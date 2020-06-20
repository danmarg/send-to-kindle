import boto3
import email
import json
import re
from base64 import b64decode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib import parse

from newspaper import Article

RE = r'''((?:http|https)://(?:[\w_-]+(?:(?:\.[\w_-]+)+))(?:[\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])?)'''


def lambda_handler(event, context):
    rec = json.loads(event['Records'][0]['Sns']['Message'])
    dst = rec['mail']['destination']
    headers = rec['mail']['headers']
    body = b64decode(rec['content'])
    msg = email.message_from_bytes(body)

    urls = []
    pdfs = []
    for part in msg.walk():
        if part.get_content_type() == 'text/plain':
            urls += re.findall(RE, part.as_string())
        elif part.get_content_type() == 'application/pdf':
            pdfs.append(part)

    if not urls and not pdfs:
        print('No URLs or PDFs!')
        return

    subj = ''
    attach = None

    if pdfs:
        for hdr in headers:
            if hdr['name'] == 'Subject':
                subj = hdr['value']
                break
        attach = pdfs[0]
    else:
        # Take just the first URL for now.
        art = Article(urls[0])
        art.download()
        art.parse()
        subj = art.title
        attach = MIMEText(art.html)
        attach.add_header('Content-Disposition', 'attachment')
        attach.add_header('Content-Type', 'text/html; charset=UTF-8')

    # Get the Kindle destination.
    parts = dst[0].split('@')
    dst = parts[0].split('+')[1]
    dst = parse.unquote(dst)
    if '@' not in dst:  # TODO: always append @kindle.com!
        dst += '@kindle.com'

    print('Article:', art.url)
    print('Send to:', dst)

    msg = MIMEMultipart()
    msg['Subject'] = subj
    msg['From'] = 'kindle@x.af0.net'
    msg['To'] = dst
    msg.preamble = 'Multipart message.\n'
    msg.attach(attach)


    client = boto3.client('ses' )    

    resp = client.send_raw_email(
            Source='kindle@x.af0.net',
            Destinations=[dst],
            RawMessage={'Data': msg.as_string()},
        )
    print(resp)

    return {
        'statusCode': 200,
        'body': json.dumps(resp),
    }
