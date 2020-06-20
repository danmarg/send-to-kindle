import boto3
import email
import json
import re
from base64 import b64decode
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
    if msg.is_multipart():
        for p in msg.get_payload():
            urls += re.findall(RE, p.as_string())
    else:
        urls += re.findall(RE, msg.get_payload())

    # Take just the first URL for now.
    url = urls[0]
    art = Article(url)
    art.download()
    art.parse()

    # Get the Kindle destination.
    parts = dst[0].split('@')
    dst = parts[0].split('+')[1] + '@' + parts[1]
    dst = parse.unquote(dst)
    if '@' not in dst:  # TODO: always append @kindle.com!
        dst += '@kindle.com'

    print('Article:', art.title)
    print('Send to:', dst)

    client = boto3.client('ses' )    
    message_dict = { 'Data':
      'From: Send To Kindle <kindle@r.x.af0.net>\n'
      'To: ' + dst + '\n'
      'Subject: ' + a.title + '\n'
      'MIME-Version: 1.0\n'
      'Content-Type: text/html;\n\n' +
      art.html}

    resp = client.send_raw_email(
            Destination={
                'ToAddresses': [dst],
            },
            FromArn='',
            RawMessage=message_dict,
        )
    print(resp)

    return {
        'statusCode': 200,
        'body': json.dumps(resp),
    }
