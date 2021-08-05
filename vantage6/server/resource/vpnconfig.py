# -*- coding: utf-8 -*-
import logging

from flasgger import swag_from
from pathlib import Path
from http import HTTPStatus
from requests_oauthlib import OAuth2Session
import os
import json
import base64
import os
import hashlib
import re
import urllib.parse as urlparse

from vantage6.common import logger_name
from vantage6.server.resource import with_node, ServicesResources
from vantage6.server._version import __version__

module_name = logger_name(__name__)
log = logging.getLogger(module_name)


def setup(api, api_base, services):

    path = "/".join([api_base, module_name])
    log.info(f'Setting up "{path}" and subdirectories')

    api.add_resource(
        VPNConfig,
        path,
        endpoint='vpn_config',
        methods=('GET',),
        resource_class_kwargs=services
    )


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------
class VPNConfig(ServicesResources):

    @with_node
    @swag_from(
        str(Path(r"swagger/get_vpn_config.yaml")), endpoint='vpn_config'
    )
    def get(self):
        """ Return configuration to enable connection to EduVPN. """

        # obtain VPN config by calling EduVPN API
        vpn_connector = EduVPNConnector(self.config['vpn_server'])
        ovpn_config = vpn_connector.get_ovpn_config()

        return {'data': ovpn_config}, HTTPStatus.OK


class EduVPNConnector:
    """ Connector to access EduVPN API """
    def __init__(self, vpn_config):
        self.config = vpn_config
        self.session = OAuth2Session(vpn_config['client_id'])

        self.PORTAL_URL = self.config['url'][:-1] \
            if self.config['url'].endswith('/') \
            else self.config['url']
        self.API_URL = f'{self.PORTAL_URL}/api.php'

    def get_ovpn_config(self):
        """ Obtain OVPN configuration file from EduVPN API """

        # obtain access token if not set
        if not self.session.token:
            self.set_access_token()

        # get the user's profile id
        profile = self.get_profile()
        profile_id = profile['profile_list']['data'][0]['profile_id']

        # get the OVPN configuration for the selected user profile
        ovpn_config = self.get_config(profile_id)

        # get a key and certificate for the client
        cert, key = self.get_key_pair()

        # add the client credentials to the ovpn file
        ovpn_config = self._insert_keypair_into_config(ovpn_config, cert, key)
        return ovpn_config

    def set_access_token(self):
        """ Obtain an access token to enable access to EduVPN API """
        # set PKCE data (code challenge and code verifier)
        self._set_pkce()
        # login to the EduVPN portal
        self._login()
        # call the authorization route of EduVPN to get authorization code
        self._authorize()
        # use authorization code to obtain token
        self.session.token = self._get_token()

    def _set_pkce(self):
        """ Generate PKCE code verifier and challenge """
        # set PKCE verifier
        self.code_verifier = \
            base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
        self.code_verifier = re.sub('[^a-zA-Z0-9]+', '', self.code_verifier)

        # set PKCE challenge based on the verifier
        self.code_challenge = \
            hashlib.sha256(self.code_verifier.encode('utf-8')).digest()
        self.code_challenge = \
            base64.urlsafe_b64encode(self.code_challenge).decode('utf-8')
        self.code_challenge = self.code_challenge.replace('=', '')

    def _login(self):
        """ Login to the EduVPN user portal in the requests session """
        post_data = {
            'userName': self.config['portal_username'],
            'userPass': self.config['portal_userpass'],
            '_form_auth_redirect_to': self.config['url']
        }
        self.session.post(
            f'{self.PORTAL_URL}/_form/auth/verify', data=post_data
        )

    def _authorize(self):
        """ Call authorization route of EduVPN to get authorization code """
        params = {
            'client_id': self.config['client_id'],
            'redirect_uri': self.config['redirect_url'],
            'response_type': 'code',
            'scope': 'config',
            'state': 'some_string',
            'code_challenge_method': 'S256',
            'code_challenge': self.code_challenge,
        }
        # Call authorization route, but prevent redirect. By preventing the
        # redirect, the authorization code can be used in the current session
        # which allows us to use the PKCE code verifier without having to save
        # it in e.g. database or session state.
        response = self.session.get(
            f'{self.PORTAL_URL}/_oauth/authorize',
            params=params,
            allow_redirects=False
        )

        # get the authorization token from the request headers
        redirected_uri = response.headers['Location']
        parsed_url = urlparse.urlparse(redirected_uri)
        self.code = urlparse.parse_qs(parsed_url.query)['code']

    def _get_token(self):
        """ Use authorization code to obtain a token from the EduVPN portal """
        data = {
            'code': self.code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.config['redirect_url'],
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'code_verifier': self.code_verifier,
        }
        r = self.session.post(
            f'{self.PORTAL_URL}/oauth.php/token',
            data=data,
            auth=(self.config['client_id'], self.config['client_secret'])
        )
        return json.loads(r.content.decode('utf-8'))

    def _insert_keypair_into_config(
        self, ovpn_config: str, cert: str, key: str
    ):
        """
        Insert the client's key pair into the correct place into the OVPN file
        (i.e. before the <tls-crypt> field)

        Parameters
        ----------
        config : str
            The OVPN configuration information without client keys
        cert : str
            The client's certificate
        key: str
            The client's private key

        Returns
        -------
        str
            A complete OVPN config file contents, including client's key-pair
        """
        insert_loc = ovpn_config.find('<tls-crypt>')
        return (
            ovpn_config[:insert_loc] +
            '<cert>\n' + cert + '\n</cert>\n' +
            '<key>\n' + key + '\n</key>\n' +
            ovpn_config[insert_loc:]
        )

    def get_profile(self):
        """ Call the profile_list route of EduVPN API """
        response = self.session.get(f'{self.API_URL}/profile_list')
        return json.loads(response.content.decode('utf-8'))

    def get_config(self, profile_id):
        """ Call the profile_config route of EduVPN API

        Parameters
        ----------
        profile_id: str
            An EduVPN user's profile_id obtained from the /profile_list route
        """
        params = {
            'profile_id': profile_id
        }
        response_config = self.session.get(
            f'{self.API_URL}/profile_config', params=params
        )
        return response_config.content.decode('utf-8')

    def get_key_pair(self):
        """ Call the create_keypair route of EduVPN API """
        response_keypair = self.session.post(f'{self.API_URL}/create_keypair')
        ovpn_keypair = json.loads(response_keypair.content.decode('utf-8'))
        cert = ovpn_keypair['create_keypair']['data']['certificate']
        key = ovpn_keypair['create_keypair']['data']['private_key']
        return cert, key
