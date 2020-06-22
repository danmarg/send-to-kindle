import argparse 

from lambda_function import fetch_and_format

parser = argparse.ArgumentParser(description='Download and format a URL.')
parser.add_argument('--url', type=str, nargs=1,
                    help='URL to download')
parser.add_argument('--no-image', dest='no_image', action='store_true')

args = parser.parse_args()
title, body = fetch_and_format(args.url[0], fetch_img=(not args.no_image))
print(body)
