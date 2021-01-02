import boto3
import email
import json
import re
import urllib
from base64 import b64encode, b64decode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.entities import codepoint2name
from urllib import parse

import tldextract
from newspaper import Article, Config

RE = r'''((?:http|https)://(?:[\w_-]+(?:(?:\.[\w_-]+)+))(?:[\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])?)'''

# Allow list of manually-sent-to address domains, to avoid being a spam relay.
ALLOWED_DOMAINS = ['af0.net', 'kindle.com']

USERAGENT  = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'


def decode_to_entity(s):
    t = ''
    for i in s:
        if ord(i) in codepoint2name:
            name = codepoint2name.get(ord(i))
            t += '&' + name + ';'
        else:
            t += i
    return t

def fetch_image_to_b64(url):
    req = urllib.request.Request(url, headers={'User-Agent': USERAGENT})
    with urllib.request.urlopen(req) as resp:
        ctype = resp.headers.get_content_type()
        ext = ctype.split('/')[1]
        raw = resp.read()
        return 'data:' + ctype + ';base64,' + str(b64encode(raw), 'utf-8')

def fetch_and_format(url, fetch_img=True):
    cfg = Config()
    cfg.keep_article_html = True
    cfg.browser_user_agent = USERAGENT
    cfg.drop_text_node = lambda x: x in ('', 'Advertisement', 'advertisement')
    def transform_img(i):
        try:
            i.attrib['src'] = fetch_image_to_b64(i.attrib['src'])
        except Exception as e:
            # print(e)
            pass
    cfg.element_transformers['img'] = transform_img
    def transform_picture(i):
        try:
            img = i.find('img')
            if img is not None:
                i.tag = 'img'
                for k, v in img.items():
                    i.attrib[k] = v
                if 'src' in i.attrib:
                    i.attrib['src'] = fetch_image_to_b64(i.attrib['src'])
        except Exception as e:
            # print(e)
            pass
    cfg.element_transformers['picture'] = transform_picture

    art = Article(url, config=cfg)
    art.download()
    art.parse()
    title = decode_to_entity(art.title)
    # TODO: Newspaper3k parses the same author multiple times. Fix!
    author = art.authors[0] if art.authors else ''
    publish_date = art.publish_date.strftime('%B %d %Y') if art.publish_date else ''
    source = tldextract.extract(url).registered_domain  # Is there a better source for this?
    text = art.article_html
    doc = f'''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><html>
    <head>
    <META http-equiv="Content-Type" content="text/html; charset=utf-8">
    <META name="author" content="{author}">
    <META name="title" content="{title}">
    </head>
    <body><div>
    <h1>{title}</h1>
    <h3>{author}</h3>
    <h4><a href='{url}'>{source}</a></h4>
    <h4>{publish_date}</h4>
    {text}
    </body>
    </html>'''
    return art.title, doc

def html_as_mime_attachment(title, html):
    filename = ''.join([c for c in title
                        if c.isalpha() or c.isdigit() or c in (' ', '_', '-')]).rstrip()
    attach = MIMEText(html, 'html', 'utf-8')
    attach.add_header('Content-Disposition', 'attachment',
            filename=filename + '.html')
    return attach

def lambda_handler(event=None, context=None, dst=None, urls=[], pdfs=[], do_mail=True):
    if event:
        rec = json.loads(event['Records'][0]['Sns']['Message'])
        dst = rec['mail']['destination']
        headers = rec['mail']['headers']
        body = b64decode(rec['content'])
        msg = email.message_from_bytes(body)

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
        print('Disallowed destination:\n', body)
        return

    print('Article:', urls[0])
    print('Send to:', dst)

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subj
    msg['From'] = '<kindle@x.af0.net>'
    msg['To'] = dst
    msg.attach(MIMEText('Multipart message.'))

    for a in attach:
      msg.attach(a)

    if not do_mail:
        print(msg)
        return

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
