#!/usr/bin/env python3

"""
generate signed urls or cookies for AWS CloudFront

pip install botocore rsa requests
"""
import sys
from datetime import datetime, timedelta
import functools
import pathlib
from urllib.parse import urlsplit

from botocore.signers import CloudFrontSigner
import requests
import rsa


class CloudFrontUtil:
    def __init__(self, private_key_path: str, key_id: str):
        """
        :param private_key_path: str, the path of private key which generated by openssl command line
        :param key_id: str, CloudFront -> Key management -> Public keys
        """
        self.key_id = key_id

        with open(private_key_path, 'rb') as fp:
            priv_key = rsa.PrivateKey.load_pkcs1(fp.read())

        # NOTE: CloudFront use RSA-SHA1 for signing URLs or cookies
        self.rsa_signer = functools.partial(
            rsa.sign, priv_key=priv_key, hash_method='SHA-1'
        )
        self.cf_signer = CloudFrontSigner(key_id, self.rsa_signer)

    def generate_presigned_url(self, url: str, expire_at: datetime) -> str:
        # Create a signed url that will be valid until the specfic expiry date
        # provided using a canned policy.
        return self.cf_signer.generate_presigned_url(url, date_less_than=expire_at)

    def generate_signed_cookies(self, url: str, expire_at: datetime) -> str:
        policy = self.cf_signer.build_policy(url, expire_at).encode('utf8')
        policy_64 = self.cf_signer._url_b64encode(policy).decode('utf8')

        signature = self.rsa_signer(policy)
        signature_64 = self.cf_signer._url_b64encode(signature).decode('utf8')
        return {
            "CloudFront-Policy": policy_64,
            "CloudFront-Signature": signature_64,
            "CloudFront-Key-Pair-Id": self.key_id,
        }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Syntax: <path_to_private_key> [url_path_to_pull]')
        exit(1)

    ART_CLOUDFRONT_DOMAIN = 'https://d2jiepz2fi8hgn.cloudfront.net'

    if len(sys.argv) > 2:
        path = sys.argv[2]
    else:
        path = 'index.html'

    key_path = pathlib.Path(sys.argv[1])
    if not key_path.exists():
        print(f'File does not exist: {key_path}')
        exit(1)

    private_key_path = str(key_path)
    key_id = 'K3M7WLN23IL48K'  # CloudFront -> Key management -> Public keys, the value of `ID` field
    resource = ART_CLOUDFRONT_DOMAIN + '/*'  # your file's cdn url
    expire_at = datetime.now() + timedelta(days=35*365)

    cfu = CloudFrontUtil(private_key_path, key_id)

    # signed cookies
    signed_cookies = cfu.generate_signed_cookies(resource, expire_at)

    url = ART_CLOUDFRONT_DOMAIN + '/' + path
    r = requests.get(url, cookies=signed_cookies)

    import pprint
    print('Cookies:\n')
    pprint.pprint(signed_cookies)

    print('\nFlat form for cluster secret')
    cloudfront_signed_cookies_content = 'set $CLOUDFRONT_SIGNED_COOKIES "'
    for k, v in signed_cookies.items():
        cloudfront_signed_cookies_content += f'{k}={v}; '
    cloudfront_signed_cookies_content = cloudfront_signed_cookies_content.strip() + '";'
    print(cloudfront_signed_cookies_content)

    print('\nTest URL:\n')
    print(f'using signed cookie: {path}, {r.status_code}, {r.content}')
