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

# Allow list of manually-sent-to address domains, to avoid being a spam relay.
ALLOWED_DOMAINS = ['af0.net', 'kindle.com']

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
    for hdr in headers:
        if hdr['name'] == 'Subject':
            subj = hdr['value']
            break

    attach = None

    if pdfs:
        attach = pdfs[0]
    else:
        # Take just the first URL for now.
        art = Article(urls[0])
        art.download()
        art.parse()
        if not subj:
          subj = art.title
        attach = MIMEText(art.html, 'html', 'utf-8')
        attach.add_header('Content-Disposition', 'attachment',
                filename=subj + '.html')
        attach.add_header('Content-Type', 'text/html; charset=UTF-8')

    # Get the Kindle destination.
    print('Raw destination:', dst[0])
    if '@' not in dst[0] or '+' not in dst[0]:
        print('Unexpected message:\n', body)
        return
    parts = dst[0].split('@')
    dst = parts[0].split('+')[1]
    dst = parse.unquote(dst)
    if '@' not in dst:  # TODO: always append @kindle.com!
        dst += '@kindle.com'
    elif dst.split('@')[1] not in ALLOWED_DOMAINS:
        print('Disallowed destionation:\n', body)

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
