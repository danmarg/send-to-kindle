import boto3
import email
import json
import re
import urllib
from base64 import b64encode, b64decode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib import parse

from newspaper import Article, Config

RE = r'''((?:http|https)://(?:[\w_-]+(?:(?:\.[\w_-]+)+))(?:[\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])?)'''

# Allow list of manually-sent-to address domains, to avoid being a spam relay.
ALLOWED_DOMAINS = ['af0.net', 'kindle.com']

def fetch_and_format(url, fetch_img=True):
    cfg = Config()
    cfg.keep_article_html = True
    art = Article(url, config=cfg)
    art.download()
    art.parse()
    # Format text into HTML. This is crappy--it loses things like boldface
    # and italics--and could be replaced with a library that does this
    # better! Images would also be nice...
    title = art.title
    # TODO: Newspaper3k parses the same author multiple times. Fix!
    author = art.authors[0] if art.authors else ''
    publish_date = art.publish_date.strftime('%B %d %Y') if art.publish_date else ''
    text = art.article_html
    image = ''
    if art.top_img and fetch_img:
        with urllib.request.urlopen(art.top_img) as resp:
            try:
                ctype = resp.headers.get_content_type()
                ext = ctype.split('/')[1]
                raw = resp.read()
                image = '<img src="data:' + ctype + ';base64,' + str(b64encode(raw), 'utf-8') + '"/>'
            except Exception as e:
                print(e)
                pass

    doc = f'''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><html>
    <head>
    <META http-equiv="Content-Type" content="text/html; charset=utf-8">
    <META name="author" content="{author}">
    <META name="title" content="{title}">
    </head>
    <body><div>
    <h1>{title}</h1>
    <h3>{author}</h3>
    <h4>{publish_date}</h4>
    {image}
    {text}
    </body>
    </html>'''
    return title, doc

def html_as_mime_attachment(title, html):
    attach = MIMEText(html, 'html', 'utf-8')
    attach.add_header('Content-Disposition', 'attachment',
            filename=title + '.html')
    attach.add_header('Content-Type', 'text/html; charset=UTF-8')
    return attach

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
        subj = 'convert'  # Convert to AZW.
        attach = pdfs
    else:
        subj = ''
        title, html = fetch_and_format(urls[0])  # Take just the first URL.
        attach = [html_as_mime_attachment(title, html)]

    # Get the Kindle destination.
    print('Raw destination:', dst[0])
    if '@' not in dst[0] or '+' not in dst[0]:
        print('Unexpected message:\n', body)
        return
    parts = dst[0].split('@')
    dst = parts[0].split('+')[1]
    dst = parse.unquote(dst)
    if '@' not in dst:
        dst += '@kindle.com'
    elif dst.split('@')[1] not in ALLOWED_DOMAINS:
        print('Disallowed destionation:\n', body)

    print('Article:', urls[0])
    print('Send to:', dst)

    msg = MIMEMultipart('related')
    msg['Subject'] = subj
    msg['From'] = '<kindle@x.af0.net>'
    msg['To'] = dst
    msg.preamble = 'Multipart message.\n'
    for a in attach:
      msg.attach(a)


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
