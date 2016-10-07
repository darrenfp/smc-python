"""
Session module for tracking existing connection state to SMC
"""
import re
import json
import requests
import logging
from smc.api.web import SMCAPIConnection
from smc.api.exceptions import SMCConnectionError, ConfigLoadError,\
    UnsupportedEntryPoint
from smc.api.configloader import load_from_file

logger = logging.getLogger(__name__)

class Session(object):
    def __init__(self):
        self._cache = None
        self._session = None
        self._connection = None
        self._url = None
        self._api_key = None
        self._timeout = 10
        self.__http_401 = 0

    @property
    def api_version(self):
        """ API Version """
        return self.cache.api_version
    
    @property
    def session(self):
        """ Session for this interpreter """
        return self._session

    @property
    def session_id(self):
        """ Session ID representation """
        return self.session.cookies

    @property
    def connection(self):
        return self._connection

    @property
    def cache(self):
        if self._cache is not None:
            return self._cache
        else:
            self._cache = SessionCache()
            return self._cache

    @property
    def element_filters(self):
        """ Filters for entry points in the elements node. 
        These can be used as search filter_contexts.
        
        :return: list available filters
        """
        return self.cache.get_element_filters()
    
    @property
    def url(self):
        """ SMC URL """
        return self._url
    
    @property
    def api_key(self):
        """ SMC Client API key """
        return self._api_key
    
    @property
    def timeout(self):
        return self._timeout
    
    def login(self, url=None, api_key=None, api_version=None,
              timeout=None, **kwargs):
        """
        Login to SMC API and retrieve a valid session.
        Session will be re-used when multiple queries are required.
        
        An example login and logout session::
        
            from smc import session   
            session.login(url='http://1.1.1.1:8082', api_key='SomeSMCG3ener@t3dPwd')
            .....do stuff.....
            session.logout()
            
        :param str url: ip of SMC management server
        :param str api_key: API key created for api client in SMC
        :param api_version (optional): specify api version
        :param int timeout: (optional): specify a timeout for initial connect; (default 10)

        Logout should be called to remove the session immediately from the
        SMC server.
        #TODO: Implement SSL tracking
        """
        if url and api_key:
            self._url = url
            self._api_key = api_key
            if timeout:
                self._timeout = timeout
        else:
            try:
                self.login(**load_from_file())
            except ConfigLoadError:
                raise
                   
        self.cache.get_api_entry(self.url, api_version, 
                                 timeout=self.timeout)

        s = requests.session() #no session yet
        r = s.post(self.cache.get_entry_href('login'),
                   json={'authenticationkey': self.api_key},
                   headers={'content-type': 'application/json'})
        if r.status_code == 200:
            self._session = s #session creation was successful
            logger.debug("Login succeeded and session retrieved: %s", \
                         self.session_id)
            self._connection = SMCAPIConnection(self)
        else:
            raise SMCConnectionError("Login failed, HTTP status code: %s" \
                                     % r.status_code)
    def logout(self):
        """ Logout session from SMC """
        if self.session:
            r = self.session.put(self.cache.get_entry_href('logout'))
            if r.status_code == 204:
                logger.info("Logged out successfully")
            else:
                if r.status_code == 401:
                    logger.error("Logout failed, session has already expired, "
                                 "status code: %s", (r.status_code))
                else:
                    logger.error("Logout failed, status code: %s", r.status_code)
    
    def http_unauthorized(self):
        """
        Refresh SMC session if it timed out. This may be the case if the CLI
        is being used and the user was idle. SMC has a time out value for API
        client sessions (configurable). Refresh will use the previously saved url
        and apikey and get a new session and http_unauthorized the api_entry cache
        """
        self.__http_401 += 1
        if self.session is not None: #user has logged in previously
            logger.info("Session http_unauthorized called, received an HTTP 401 unauthorized")
            if self.__http_401 >= 2:
                #Exit to prevent inadvertent looping if an http 401 was received.
                #Try to re-authenticate once in case of longer running app's that may
                #have had the SMC session time out
                raise SMCConnectionError("Unauthorized. Too many HTTP 401 requests received.")
            self.login(url=self.url, 
                       api_key=self.api_key, 
                       api_version=self.api_version)
        else:
            raise SMCConnectionError("No previous SMC session found. "
                                     "This will require a new login attempt")

class SessionCache(object):
    def __init__(self):
        self.api_entry = None
        self.api_version = None

    def get_api_entry(self, url, api_version=None, timeout=10):
        """
        Called internally after login to get cache of SMC entry points
        
        :param: str url: URL for SMC 
        :param str api_version: if specified, use this version, or use latest
        """
        try:
            if api_version is None:
                r = requests.get('%s/api' % url, timeout=timeout) #no session required
                j = json.loads(r.text)
                versions = []
                for version in j['version']:
                    versions.append(version['rel'])
                versions = [float(i) for i in versions]
                api_version = max(versions)

            #else api_version was defined
            logger.info("Using SMC API version: %s", api_version)
            smc_url = url + '/' + str(api_version)

            r = requests.get('%s/api' % (smc_url), timeout=timeout)
            if r.status_code==200:
                j = json.loads(r.text)
                self.api_version = api_version
                logger.debug("Successfully retrieved API entry points from SMC")
            else:
                raise SMCConnectionError("Error occurred during initial api "
                                         "request, json was not returned. "
                                         "Return data was: %s" % r.text)
            self.api_entry = j['entry_point']

        except requests.exceptions.RequestException, e:
            raise SMCConnectionError(e)

    def get_entry_href(self, verb):
        """
        Get entry point from entry point cache
        Call get_all_entry_points to find all available entry points. 
        
        :param str verb: top level entry point into SMC api
        :return dict: meta data for specified entry point
        :raises: :py:class:`smc.api.exceptions.UnsupportedEntryPoint`
        """
        if self.api_entry:
            href = None
            for entry in self.api_entry:
                if entry.get('rel') == verb:
                    href = entry.get('href', None)
            if not href:
                raise UnsupportedEntryPoint(
                        "The specified entry point '{}' was not found in this "
                        "version of the SMC API. Check the element documentation "
                        "to determine the correct version and specify the api_version "
                        "parameter during session.login() if necessary. Current api version "
                        "is {}".format(verb, self.api_version))
            else:
                return href      
        else:
            raise SMCConnectionError("No entry points found, it is likely "
                                     "there is no valid login session.")

    def get_element_filters(self):
        """
        Build a list of filter contexts for entry points related to elements.
        These filters can be used in the filter_context parameter on search methods 
        that support them.
        
        :return: list names of each available filter context on the element node
        """
        regex = self.get_entry_href('elements') + r"/(.*)"
        element_filters=[m.group(1)
                         for ep in self.api_entry
                         for m in re.finditer(regex, ep.get('href'))]
        return element_filters

    def get_all_entry_points(self):
        """ Returns all entry points into SMC api """
        return self.api_entry