import argparse 

from lambda_function import fetch_and_format, lambda_handler

parser = argparse.ArgumentParser(description='Download and format a URL.')
parser.add_argument('--url', type=str, nargs=1,
                    help='URL to download')
parser.add_argument('--no-image', dest='no_image', action='store_true')
parser.add_argument('--generate-email', dest='generate_email', action='store_true')

args = parser.parse_args()
if args.generate_email:
    lambda_handler(dst=['test+test@example.com'], urls=args.url, do_mail=False, fetch_img=(not args.no_image))
else:
    title, body = fetch_and_format(args.url[0], fetch_img=(not args.no_image))
    print(body)
