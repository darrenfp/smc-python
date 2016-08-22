from smc.elements.element import SMCElement, Blacklist, VirtualResource
from smc.elements.interfaces import VirtualPhysicalInterface, PhysicalInterface, Interface
import smc.actions.search as search
import smc.api.common as common_api
from smc.elements.helpers import find_link_by_name
from smc.api.web import CreateEngineFailed, LoadEngineFailed
from smc.elements.system import SystemInfo

def get_element_etag(href):
    return search.element_by_href_as_smcresult(href)

class Engine(object):
    """
    Instance level attributes
    :ivar: name: name of engine
    
    Engine has resources::
    
        :ivar: list nodes: (Node) nodes associated with this engine
        :ivar: list interface: (Interface) interfaces for this engine
        :ivar: internal_gateway: (InternalGateway) engine level VPN settings
        :ivar: physical_interface: (PhysicalInterface) access to physical interface settings
    """
    def __init__(self, name):
        self.name = name
        
    @classmethod
    def create(cls, name, node_type, 
               physical_interfaces,
               nodes=1,
               log_server_ref=None, 
               domain_server_address=None):
        """
        Create will return the engine configuration as a dict that is a 
        representation of the engine. The creating class will also add 
        engine specific requirements before adding it to an SMCElement
        and sending to SMC (which will serialize the dict to json).
        
        :param name: name of engine
        :param str node_type: comes from class attribute of engine type
        :param dict physical_interfaces
        :param int nodes: number of nodes for engine
        :param str log_server_ref: href of log server
        :param list domain_server_address
        """
        cls.nodes = []
        nodes = nodes
        for nodeid in range(1, nodes+1): #start at nodeid=1
            cls.nodes.append(Node.create(name, node_type, nodeid))
        
        try:
            cls.domain_server_address = []
            rank_i = 0
            for entry in domain_server_address:
                cls.domain_server_address.append(
                                    {"rank": rank_i, "value": entry})
        except (AttributeError, TypeError):
            pass
        
        if not log_server_ref: #Set log server reference, if not explicitly set
            log_server_ref = SystemInfo().first_log_server()
        
        engine = Engine(name)                     
        base_cfg = {'name': name,
                    'nodes': cls.nodes,
                    'domain_server_address': cls.domain_server_address,
                    'log_server_ref': log_server_ref,
                    'physicalInterfaces': physical_interfaces}
        for k,v in base_cfg.items():
            setattr(engine, k, v)
        
        return vars(engine)
          
    def load(self):
        """ When engine is loaded, save the attributes that are
        needed. Get data like nodes from engine json so multiple
        queries aren't required. Call this to reload settings, useful
        if changes are made and new configuration is needed.
        raw_json: stores the engine raw json data
        nodes: link to nodes (has-a)
        link: engine level href links
        """
        result = search.element_as_json_with_etag(self.name)
        if result:
            engine = Engine(self.name)
            engine.raw_json = result.json
            engine.nodes = []
            engine.link = []
            for node in engine.raw_json.get('nodes'):
                for node_type, data in node.iteritems():
                    new_node = Node(node_type, data)
                    engine.nodes.append(new_node)
            engine.link.extend(engine.raw_json.get('link'))
            return engine
        else:
            raise LoadEngineFailed("Cannot load engine name: %s, please ensure the name is correct"
                               " and the engine exists." % self.name)
    
    def modify_attribute(self, attribute):
        """
        :param attribute: {'key': 'value'}
        """
        self.raw_json.update(attribute)    
    
    def node(self):
        """ Return node/s references for this engine. For a cluster this will
        contain multiple entries. 
        
        :method: GET
        :return: dict list with reference {href, name, type}
        """
        return search.element_by_href_as_json(
                        find_link_by_name('nodes', self.link))
        
    def alias_resolving(self):
        """ Alias definitions defined for this engine 
        Aliases can be used in rules to simplify multiple object creation
        
        :method: GET
        :return: dict list [{alias_ref: str, 'cluster_ref': str, 'resolved_value': []}]
        """
        return search.element_by_href_as_json(
                        find_link_by_name('alias_resolving', self.link)) 
    
    def blacklist(self, src, dst, duration=3600):
        """ Add blacklist entry to engine node by name
    
        :method: POST
        :param name: name of engine node or cluster
        :param src: source to blacklist, can be /32 or network cidr
        :param dst: dest to deny to, 0.0.0.0/32 indicates all destinations
        :param duration: how long to blacklist in seconds
        :return: SMCResult (href attr set with blacklist entry)
        """
        element = Blacklist(src, dst, duration)
        element.href = find_link_by_name('blacklist', self.link)
        return element.create()
    
    def blacklist_flush(self):
        """ Flush entire blacklist for node name
    
        :method: DELETE
        :param name: name of node or cluster to remove blacklist
        :return: SMCResult (msg attribute set if failure)
        """
        return common_api.delete(find_link_by_name('flush_blacklist', self.link))
    
    def add_route(self, gateway, network):
        """ Add a route to engine. Specify gateway and network. 
        If this is the default gateway, use a network address of
        0.0.0.0/0.
        
        .. note: This will fail if the gateway provided does not have a 
                 corresponding interface on the network.
        
        :method: POST
        :param gateway: gateway of an existing interface
        :param network: network address in cidr format
        :return: SMCResult
        """
        return SMCElement(
                    href=find_link_by_name('add_route', self.link),
                    params={'gateway': gateway, 
                            'network': network}).create()
                                  
    def routing(self):
        """ Retrieve routing json from engine node
        
        :method: GET
        :return: json representing routing configuration
        """
        return search.element_by_href_as_json(
                        find_link_by_name('routing', self.link))
    
    def routing_monitoring(self):
        """ Return route information for the engine, including gateway, networks
        and type of route (dynamic, static)
        
        :method: GET
        :return: dict of dict list entries representing routes
        """
        return search.element_by_href_as_json(
                        find_link_by_name('routing_monitoring', self.link))
        
    def antispoofing(self):
        """ Antispoofing interface information. By default is based on routing
        but can be modified in special cases
        
        :method: GET
        :return: dict of antispoofing settings per interface
        """
        return search.element_by_href_as_json(
                        find_link_by_name('antispoofing', self.link))
    
    @property
    def internal_gateway(self):
        """ Engine level VPN gateway reference
    
        :method: GET
        :return: dict list of internal gateway references
        """
        result = search.element_by_href_as_json(
                    find_link_by_name('internal_gateway', self.link))
        for gw in result:
            igw = InternalGateway(
                        **search.element_by_href_as_json(gw.get('href')))
        return igw
    
    def virtual_resource(self):
        """ Master Engine only 
        
        :return: list of dict { href, name, type } which hold virtual resources
                 assigned to the master engine
        """
        return search.element_by_href_as_json(
                        find_link_by_name('virtual_resources', self.link))
    
    @property    
    def interface(self):
        """ Get all interfaces, including non-physical interfaces such
        as tunnel or capture interfaces. These are returned as Interface 
        objects and can be used to load specific interfaces to modify, etc.

        :method: GET
        :return: list Interface: returns a top level Interface representing each
                 configured interface on the engine. 
        
        See :py:class:`smc.elements.engines.Interface` for more info
        """
        intf = search.element_by_href_as_json(
                        find_link_by_name('interfaces', self.link))
        interfaces=[]
        for interface in intf:
            interfaces.append(Interface(**interface))
        return interfaces
    
    @property
    def physical_interface(self):
        """ Returns a PhysicalInterface. This property can be used to
        add physical interfaces to the engine. For example::
        
            engine.physical_interface.add_single_node_interface(....)
            engine.physical_interface.add_node_interface(....)
       
        :method: GET
        :return: PhysicalInterface: for manipulating physical interfaces
        """
        href = find_link_by_name('physical_interface', self.link)
        return PhysicalInterface(callback=SMCElement(href=href))
        
    def virtual_physical_interface(self):
        """ Master Engine virtual instance only
        
        A virtual physical interface is for a master engine virtual instance.
        
        :method: GET
        :return: list of dict entries with href,name,type or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('virtual_physical_interface', self.link))
    
    def tunnel_interface(self):
        """ Get only tunnel interfaces for this engine node.
        
        :method: GET
        :return: list of dict entries with href,name,type, or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('tunnel_interface', self.link)) 
    
    def modem_interface(self):
        """ Get only modem interfaces for this engine node.
        
        :method: GET
        :return: list of dict entries with href,name,type, or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('modem_interface', self.link))
    
    def adsl_interface(self):
        """ Get only adsl interfaces for this engine node.
        
        :method: GET
        :return: list of dict entries with href,name,type, or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('adsl_interface', self.link))
    
    def wireless_interface(self):
        """ Get only wireless interfaces for this engine node.
        
        :method: GET
        :return: list of dict entries with href,name,type, or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('wireless_interface', self.link))
    
    def switch_physical_interface(self):
        """ Get only switch physical interfaces for this engine node.
        
        :method: GET
        :return: list of dict entries with href,name,type, or None
        """
        return search.element_by_href_as_json(
                        find_link_by_name('switch_physical_interface', self.link))
    
    def refresh(self, wait_for_finish=True):
        """ Refresh existing policy on specified device. This is an asynchronous 
        call that will return a 'follower' link that can be queried to determine 
        the status of the task. 
        
        See :func:`async_handler` for more information on how to obtain results
        
        Last yield is result href; if wait_for_finish=False, the only yield is 
        the follower href
        
        :method: POST
        :param wait_for_finish: whether to wait in a loop until the upload completes
        :return: generator yielding updates on progress
        """
        element = SMCElement(
                    href=find_link_by_name('refresh', self.link)).create()
        return common_api.async_handler(element.json.get('follower'), 
                                        wait_for_finish)
    #TODO: When node is not initialized, should terminate rather than let the async
    #handler loop, check for that status or wait_for_finish=False
    def upload(self, policy=None, wait_for_finish=True):
        """ Upload policy to existing engine. If no policy is specified, and the engine
        has already had a policy installed, this policy will be re-uploaded. 
        
        This is typically used to install a new policy on the engine. If you just
        want to re-push an existing policy, call :func:`refresh`
        
        :param policy: name of policy to upload to engine
        :param wait_for_finish: whether to wait for async responses
        :return: generator yielding updates on progress
        """
        if not policy: #if policy not specified SMC seems to apply some random policy: bug?
            for node in self.nodes:
                policy = node.status().get('installed_policy')
                if policy:
                    break
        element = SMCElement(
                    href=find_link_by_name('upload', self.link),
                    params={'filter': policy}).create()
        return common_api.async_handler(element.json.get('follower'), 
                                        wait_for_finish)
    
    def generate_snapshot(self, filename='snapshot.zip'):
        """ Generate and retrieve a policy snapshot from the engine
        This is blocking as file is downloaded
        
        :method: GET
        :param filename: name of file to save file to, including directory path
        :return: None
        """
        href = find_link_by_name('generate_snapshot', self.link)
        return common_api.fetch_content_as_file(href, filename=filename)
    
    def snapshot(self):
        """ References to policy based snapshots for this engine, including
        the date the snapshot was made
        
        :method: GET
        :return: list of dict with {href,name,type}
        """
        return search.element_by_href_as_json(
                        find_link_by_name('snapshots', self.link))
    
    def export(self, filename='export.zip'): 
        """ Generate export of configuration. Export is downloaded to
        file specified in filename parameter.
        
        :mathod: POST
        :param filename: if set, the export will download the file. 
        :return: href of export, file download
        """
        element = SMCElement(
                    href=find_link_by_name('export', self.link),
                    params={'filter': self.name}).create()
        
        href = next(common_api.async_handler(element.json.get('follower'), 
                                             display_msg=False))

        return common_api.fetch_content_as_file(href, filename)
      
class Node(object):
    """ 
    Node settings to make each engine node controllable individually.
    When Engine().load() is called, setattr will set all instance attributes
    with the contents of the node json. Very few would benefit from being
    modified with exception of 'name'. To change a top level attribute, you
    would call node.modify_attribute({'name': 'value'})
    Engine will have a 'has-a' relationship with node and stored as the
    nodes attribute
    :ivar: name: name of node
    :ivar: engine_version: software version installed
    :ivar: nodeid: node id, useful for commanding engines
    :ivar: disabled: whether node is disabled or not
    """
    node_type = None
    
    def __init__(self, node_type, mydict):
        Node.node_type = node_type
        for k, v in mydict.items():
            setattr(self, k, v)
    
    @classmethod
    def create(cls, name, node_type, nodeid=1):
        """
        :param name
        :param node_type
        :param nodeid
        """  
        node = Node(node_type,
                        {'activate_test': True,
                         'disabled': False,
                         'loopback_node_dedicated_interface': [],
                         'name': name + ' node '+str(nodeid),
                         'nodeid': nodeid})
        return({node_type: 
                vars(node)}) 

    def modify_attribute(self, attribute):
        """ Modify attribute/value pair of base node
        :ivar name
        """
        self.__dict__.update(attribute)
        return SMCElement(
                    href=find_link_by_name('self', self.link),
                    json=vars(self)).update()
    
    def fetch_license(self):
        """ Fetch the node level license
        
        :return: SMCResult
        """
        return SMCElement(
                href=find_link_by_name('fetch', self.link)).create()

    def bind_license(self, license_item_id=None):
        """ Auto bind license, uses dynamic if POS is not found
        
        :param str license_item_id: license id
        :return: SMCResult
        """
        params = {'license_item_id': license_item_id}
        return SMCElement(
                href=find_link_by_name('bind', self.link), params=params).create()
        
    def unbind_license(self):
        """ Unbind license on node. This is idempotent. 
        
        :return: SMCResult 
        """
        return SMCElement(
                href=find_link_by_name('unbind', self.link)).create()
        
    def cancel_unbind_license(self):
        """ Cancel unbind for license
        
        :return: SMCResult
        """
        return SMCElement(
                href=find_link_by_name('cancel_unbind', self.link)).create()
    
    def initial_contact(self, enable_ssh=True, time_zone=None, 
                        keyboard=None, 
                        install_on_server=None, 
                        filename=None):
        """ Allows to save the initial contact for for the specified node
        
        :method: POST
        :param boolean enable_ssh: flag to know if we allow the ssh daemon on the specified node
        :param str time_zone: optional time zone to set on the specified node 
        :param str keyboard: optional keyboard to set on the specified node
        :param boolean install_on_server: optional flag to know if the generated configuration 
               needs to be installed on SMC Install server (POS is needed)
        :param str filename: filename to save initial_contact to. If this fails due to IOError,
               SMCResult.content will still have the contact data
        :return: SMCResult: with content attribute set to initial contact info
        """
        result = SMCElement(
                    href=find_link_by_name('initial_contact', self.link),
                    params={'enable_ssh': enable_ssh}).create()
      
        if result.content:
            if filename:
                import os.path
                path = os.path.abspath(filename)
                try:
                    with open(path, "w") as text_file:
                        text_file.write("{}".format(result.content))
                except IOError, io:
                    result.msg = "Error occurred saving initial contact info: %s" % io    
            return result.content
    
    def appliance_status(self):
        """ Gets the appliance status for the specified node 
        for the specific supported engine 
        
        :method: GET
        :return: list of status information
        """
        return search.element_by_href_as_json(
                find_link_by_name('appliance_status', self.link))
    
    def status(self):
        """ Basic status for individual node. Specific information such as node name,
        dynamic package version, configuration status, platform and version.
        
        :method: GET
        :return: dict of status fields returned from SMC
        """
        return search.element_by_href_as_json(
                find_link_by_name('status', self.link))
        
    def go_online(self, comment=None):
        """ Executes a Go-Online operation on the specified node 
        typically done when the node has already been forced offline 
        via :func:`go_offline`
        
        :method: PUT
        :param str comment: (optional) comment to audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('go_online', self.link),
                    params=params).update()

    def go_offline(self, comment=None):
        """ Executes a Go-Offline operation on the specified node
        
        :method: PUT
        :param str comment: optional comment to audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('go_offline', self.link),
                    params=params).update()

    def go_standby(self, comment=None):
        """ Executes a Go-Standby operation on the specified node. 
        To get the status of the current node/s, run :func:`status`
        
        :method: PUT
        :param str comment: optional comment to audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('go_standby', self.link),
                    params=params).update()

    def lock_online(self, comment=None):
        """ Executes a Lock-Online operation on the specified node
        
        :method: PUT
        :param str comment: comment for audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('lock_online', self.link),
                    params=params).update()
        
    def lock_offline(self, comment=None):
        """ Executes a Lock-Offline operation on the specified node
        Bring back online by running :func:`go_online`.
        
        :method: PUT
        :param str comment: comment for audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('lock_offline', self.link),
                    params=params).update()
    
    def reset_user_db(self, comment=None):
        """ Executes a Send Reset LDAP User DB Request operation on the 
        specified node
        
        :method: PUT
        :param str comment: comment to audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('reset_user_db', self.link),
                    params=params).update()
        
    def diagnostic(self, filter_enabled=False):
        """ Provide a list of diagnostic options to enable
        #TODO: implement filter_enabled
        
        :method: GET
        :param boolean filter_enabled: returns all enabled diagnostics
        :return: list of dict items with diagnostic info; key 'diagnostics'
        """
        return search.element_by_href_as_json(
                find_link_by_name('diagnostic', self.link))
    
    def send_diagnostic(self):
        """ Send the diagnostics to the specified node 
        Send diagnostics in payload
        """
        print "Not Yet Implemented"
        
    def reboot(self, comment=None):
        """ Reboots the specified node 
        
        :method: PUT
        :param str comment: comment to audit
        :return: SMCResult
        """
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('reboot', self.link),
                    params=params).update()
      
    def sginfo(self, include_core_files=False,
               include_slapcat_output=False):
        """ Get the SG Info of the specified node 
        ?include_core_files
        ?include_slapcat_output
        :param include_core_files: flag to include or not core files
        :param include_slapcat_output: flag to include or not slapcat output
        """
        #params = {'include_core_files': include_core_files,
        #          'include_slapcat_output': include_slapcat_output}  
        print "Not Yet Implemented"
   
    def ssh(self, enable=True, comment=None):
        """ Enable or disable SSH
        
        :method: PUT
        :param boolean enable: enable or disable SSH daemon
        :param str comment: optional comment for audit
        :return: SMCResult
        """
        params = {'enable': enable, 'comment': comment}
        return SMCElement(
                    href=find_link_by_name('ssh', self.link),
                    params=params).update()
        
    def change_ssh_pwd(self, pwd=None, comment=None):
        """
        Executes a change SSH password operation on the specified node 
        
        :method: PUT
        :param str pwd: changed password value
        :param str comment: optional comment for audit log
        :return: SMCResult
        """
        json = {'value': pwd}
        params = {'comment': comment}
        return SMCElement(
                    href=find_link_by_name('change_ssh_pwd', self.link),
                    params=params, json=json).update()

    def time_sync(self):
        """ Time synchronize node

        :method: PUT
        :return: SMCResult
        """
        return SMCElement(
                    href=find_link_by_name('time_sync', self.link)).update()
      
    def certificate_info(self):
        """ Get the certificate info of the specified node 
        
        :return: dict with links to cert info
        """
        return search.element_by_href_as_json(
                find_link_by_name('certificate_info', self.link))
    
    def __repr__(self):
        return "%s(%r)" % (self.__class__, 'name={},nodeid={}'.format(\
                                    self.name, self.nodeid))

class Layer3Firewall(object):
    """
    Represents a Layer 3 Firewall configuration.
    To instantiate and create, call 'create' classmethod as follows::
    
        engine = Layer3Firewall.create(name='mylayer3', 
                                       mgmt_ip='1.1.1.1', 
                                       mgmt_network='1.1.1.0/24')
                                       
    Set additional constructor values as necessary.       
    """ 
    node_type = 'firewall_node'
    def __init__(self, name):
        pass

    @classmethod
    def create(cls, name, mgmt_ip, mgmt_network, 
               log_server_ref=None,
               mgmt_interface=0, 
               default_nat=False,
               domain_server_address=None, zone_ref=None):
        """ 
        Create a single layer 3 firewall with management interface and DNS
        
        :param str name: name of firewall engine
        :param str mgmt_ip: ip address of management interface
        :param str mgmt_network: management network in cidr format
        :param str log_server_ref: (optional) href to log_server instance for fw
        :param int mgmt_interface: (optional) interface for management from SMC to fw
        :param list domain_server_address: (optional) DNS server addresses
        :param str zone_ref: (optional) zone name for management interface (created if not found)
        :param boolean default_nat: (optional) Whether to enable default NAT for outbound
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        """
        physical = PhysicalInterface()
        physical.add_single_node_interface(mgmt_interface,
                                           mgmt_ip, 
                                           mgmt_network,
                                           is_mgmt=True,
                                           zone_ref=zone_ref)

        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=[
                                    {PhysicalInterface.name: physical.data}], 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=1)
        if default_nat:
            engine.setdefault('default_nat', True)
       
        href = search.element_entry_point('single_fw')
        result = SMCElement(href=href, json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the engine, '
                                     'reason: {}'.format(result.msg))

class Layer2Firewall(object):
    node_type = 'fwlayer2_node'
    def __init__(self, name):
        pass
    
    @classmethod
    def create(cls, name, mgmt_ip, mgmt_network, 
               mgmt_interface=0, 
               inline_interface='1-2', 
               logical_interface='default_eth',
               log_server_ref=None, 
               domain_server_address=None, zone_ref=None):
        """ 
        Create a single layer 2 firewall with management interface and inline pair
        
        :param str name: name of firewall engine
        :param str mgmt_ip: ip address of management interface
        :param str mgmt_network: management network in cidr format
        :param int mgmt_interface: (optional) interface for management from SMC to fw
        :param str inline_interface: interfaces to use for first inline pair
        :param str logical_interface: (optional) logical_interface reference
        :param str log_server_ref: (optional) href to log_server instance 
        :param list domain_server_address: (optional) DNS server addresses
        :param str zone_ref: (optional) zone name for management interface (created if not found)
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        """
        interfaces = [] 
        physical = PhysicalInterface()
        physical.add_node_interface(mgmt_interface,
                                    mgmt_ip, mgmt_network, 
                                    is_mgmt=True,
                                    zone_ref=zone_ref)
        
        intf_href = search.element_href_use_filter(logical_interface, 'logical_interface')
        
        inline = PhysicalInterface()
        inline.add_inline_interface(inline_interface, intf_href)
        interfaces.append({PhysicalInterface.name: physical.data})
        interfaces.append({PhysicalInterface.name: inline.data})    
        
        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=interfaces, 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=1)
       
        href = search.element_entry_point('single_layer2')
        result = SMCElement(href=href, 
                            json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the engine, '
                                     'reason: {}'.format(result.msg))   

class IPS(object):
    node_type = 'ips_node'
    def __init__(self, name):
        pass
    
    @classmethod
    def create(cls, name, mgmt_ip, mgmt_network, 
               mgmt_interface='0',
               inline_interface='1-2',
               logical_interface='default_eth',
               log_server_ref=None,
               domain_server_address=None, zone_ref=None):
        """ 
        Create a single IPS engine with management interface and inline pair
        
        :param str name: name of ips engine
        :param str mgmt_ip: ip address of management interface
        :param str mgmt_network: management network in cidr format
        :param int mgmt_interface: (optional) interface for management from SMC to fw
        :param str inline_interface: interfaces to use for first inline pair
        :param str logical_interface: (optional) logical_interface reference
        :param str log_server_ref: (optional) href to log_server instance 
        :param list domain_server_address: (optional) DNS server addresses
        :param str zone_ref: (optional) zone name for management interface (created if not found)
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        """
        interfaces = []
        physical = PhysicalInterface()
        physical.add_node_interface(mgmt_interface,
                                    mgmt_ip, mgmt_network, 
                                    is_mgmt=True,
                                    zone_ref=zone_ref)
              
        intf_href = search.element_href_use_filter(logical_interface, 'logical_interface')
      
        inline = PhysicalInterface()
        inline.add_inline_interface(inline_interface, intf_href)
        interfaces.append({PhysicalInterface.name: physical.data})
        interfaces.append({PhysicalInterface.name: inline.data}) 
        
        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=interfaces, 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=1)
        
        href = search.element_entry_point('single_ips')
        result = SMCElement(href=href, 
                            json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the engine, '
                                     'reason: {}'.format(result.msg))
        
class Layer3VirtualEngine(Node):
    """ 
    Create a layer3 virtual engine and map to specified Master Engine
    Each layer 3 virtual firewall will use the same virtual resource that 
    should be pre-created.
        
    To instantiate and create, call 'create' as follows::
    
        engine = Layer3VirtualEngine.create(
                                'myips', 
                                'mymaster_engine, 
                                virtual_engine='ve-3',
                                interfaces=[{'address': '5.5.5.5', 
                                         'network_value': '5.5.5.5/30', 
                                         'interface_id': 0, 
                                         'zone_ref': ''}]
    """
    node_type = 'virtual_fw_node'
    def __init__(self, name):
        Node.__init__(self, name)
        pass

    @classmethod
    def create(cls, name, master_engine, virtual_resource, 
               interfaces, default_nat=False, outgoing_intf=0,
               domain_server_address=None, **kwargs):
        """
        :param str name: Name of this layer 3 virtual engine
        :param str master_engine: Name of existing master engine
        :param str virtual_resource: name of pre-created virtual resource
        :param list interfaces: dict of interface details
        :param boolean default_nat: Whether to enable default NAT for outbound
        :param int outgoing_intf: outgoing interface for VE. Specifies interface number
        :param list interfaces: interfaces mappings passed in            
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        """
        virt_resource_href = None #need virtual resource reference
        master_engine = Engine(master_engine).load()
        for virt_resource in master_engine.virtual_resource():
            if virt_resource.get('name') == virtual_resource:
                virt_resource_href = virt_resource.get('href')
                break
        if not virt_resource_href:
            raise CreateEngineFailed('Cannot find associated virtual resource for '
                                      'VE named: {}. You must first create a virtual '
                                      'resource for the master engine before you can associate '
                                      'a virtual engine. Cannot add VE'.format(name))
        new_interfaces=[]   
        for interface in interfaces:       
            physical = VirtualPhysicalInterface()
            physical.add_single_node_interface(interface.get('interface_id'),
                                               interface.get('address'),
                                               interface.get('network_value'),
                                               zone_ref=interface.get('zone_ref'))
            #set auth request and outgoing on one of the interfaces
            if interface.get('interface_id') == outgoing_intf:
                physical.modify_interface('single_node_interface', 
                                           outgoing=True,
                                           auth_request=True)
            new_interfaces.append({VirtualPhysicalInterface.name: physical.data})
           
            engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=new_interfaces, 
                               domain_server_address=domain_server_address,
                               log_server_ref=None, #Isn't used in VE
                               nodes=1)
            if default_nat:
                engine.update(default_nat=True)
            engine.update(virtual_resource=virt_resource_href)
            engine.pop('log_server_ref', None) #Master Engine provides this service
        
        
        href = search.element_entry_point('virtual_fw')
        result = SMCElement(href=href, json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the virtual engine, '
                                     'reason: {}'.format(result.msg))
            
class FirewallCluster(Node):
    """ 
    Firewall Cluster
    Creates a layer 3 firewall cluster engine with CVI and NDI's. Once engine is 
    created, and in context, add additional interfaces using engine.physical_interface 
    :py:class:PhysicalInterface.add_cluster_virtual_interface`
    """
    node_type = 'firewall_node'  
    def __init__(self, name):
        pass
    
    @classmethod
    def create(cls, name, cluster_virtual, cluster_mask, 
               macaddress, cluster_nic, nodes, 
               log_server_ref=None, 
               domain_server_address=None, 
               zone_ref=None):
        """
         Create a layer 3 firewall cluster with management interface and any number
         of nodes
        
        :param str name: name of firewall engine
        :param cluster_virtual: ip of cluster CVI
        :param cluster_mask: ip netmask of cluster CVI
        :param macaddress: macaddress for packet dispatch clustering
        :param cluster_nic: nic id to use for primary interface
        :param nodes: address/network_value/nodeid combination for cluster nodes  
        :param str log_server_ref: (optional) href to log_server instance 
        :param list domain_server_address: (optional) DNS server addresses
        :param str zone_ref: (optional) zone name for management interface (created if not found)
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        
        Example nodes parameter input::
            
            [{ 'address': '1.1.1.1', 
              'network_value': '1.1.1.0/24', 
              'nodeid': 1
             },
             { 'address': '2.2.2.2',
               'network_value': '2.2.2.0/24',
               'nodeid': 2
            }]          
        """
        physical = PhysicalInterface()
        physical.add_cluster_virtual_interface(cluster_nic,
                                               cluster_virtual, 
                                               cluster_mask,
                                               macaddress, 
                                               nodes, 
                                               is_mgmt=True,
                                               zone_ref=zone_ref)
        
        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=[
                                        {PhysicalInterface.name: physical.data}], 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=len(nodes))

        href = search.element_entry_point('fw_cluster')
        result = SMCElement(href=href,
                            json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the firewall, '
                                     'reason: {}'.format(result.msg))
        
class MasterEngine(object):
    """
    Creates a master engine in a firewall role. Layer3VirtualEngine should be used
    to add each individual instance to the Master Engine.
    """
    node_type = 'master_node'
    def __init__(self, name):
        pass
    
    @classmethod
    def create(cls, name, master_type,
               mgmt_interface=0, 
               log_server_ref=None, 
               domain_server_address=None):
        """
         Create a Master Engine with management interface
        
        :param str name: name of master engine engine
        :param str master_type: firewall|
        :param str log_server_ref: (optional) href to log_server instance 
        :param list domain_server_address: (optional) DNS server addresses
        :return: Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        """             
        physical = PhysicalInterface()
        physical.add_node_interface(mgmt_interface, 
                                    '2.2.2.2', '2.2.2.0/24')
        physical.modify_interface('node_interface',
                                  primary_mgt=True,
                                  primary_heartbeat=True,
                                  outgoing=True)
        
        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=[
                                        {PhysicalInterface.name: physical.data}], 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=1)      
        engine.setdefault('master_type', master_type)
        engine.setdefault('cluster_mode', 'balancing')

        href = search.element_entry_point('master_engine')
        result = SMCElement(href=href, 
                            json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the engine, '
                                     'reason: {}'.format(result.msg))

class AWSLayer3Firewall(object):
    """
    Create AWSLayer3Firewall in SMC. This is a Layer3Firewall instance that uses
    a DHCP address for the management interface. Management is expected to be
    on interface 0 and interface eth0 on the AWS AMI. 
    When a Layer3Firewall uses a DHCP interface for management, a second interface
    is required to be the interface for Auth Requests. This second interface information
    is obtained by creating the network interface through the AWS SDK, and feeding that
    to the constructor. This can be statically assigned as well.
    """
    node_type = 'firewall_node'
    def __init__(self, name):
        pass
        
    @classmethod
    def create(cls, name, interfaces,
               dynamic_interface=0,
               dynamic_index=1, 
               log_server_ref=None, 
               domain_server_address=None,
               default_nat = True, 
               zone_ref=None):
        """ 
        Create AWS Layer 3 Firewall. This will implement a DHCP
        interface for dynamic connection back to SMC. The initial_contact
        information will be used as user-data to initialize the EC2 instance. 
        
        :param str name: name of fw in SMC
        :param list interfaces: dict items specifying interfaces to create
        :param int dynamic_index: dhcp interface index (First DHCP Interface, etc)
        :param int dynamic_interface: interface ID to use for dhcp
        :return Engine
        :raises: :py:class:`smc.api.web.CreateEngineFailed`: Failure to create with reason
        Example interfaces::
            
            [{ 'address': '1.1.1.1', 
               'network_value': '1.1.1.0/24', 
               'interface_id': 1
             },
             { 'address': '2.2.2.2',
               'network_value': '2.2.2.0/24',
               'interface_id': 2
            }]   
        """
        new_interfaces = []
        dhcp_physical = PhysicalInterface()
        dhcp_physical.add_dhcp_interface(dynamic_interface,
                                         dynamic_index, primary_mgt=True)
        new_interfaces.append({PhysicalInterface.name: dhcp_physical.data})
        
        auth_request = 0
        for interface in interfaces:
            if interface.get('interface_id') == dynamic_interface:
                continue #In case this is defined, skip dhcp_interface id
            physical = PhysicalInterface()
            physical.add_single_node_interface(interface.get('interface_id'),
                                               interface.get('address'), 
                                               interface.get('network_value'))
            if not auth_request: #set this on first interface that is not the dhcp_interface
                physical.modify_interface('single_node_interface', auth_request=True)
                auth_request = 1
            new_interfaces.append({PhysicalInterface.name: physical.data})
        
        engine = Engine.create(name=name,
                               node_type=cls.node_type,
                               physical_interfaces=new_interfaces, 
                               domain_server_address=domain_server_address,
                               log_server_ref=log_server_ref,
                               nodes=1)    
        if default_nat:
            engine.setdefault('default_nat', True)
       
        href = search.element_entry_point('single_fw')
        result = SMCElement(href=href, 
                            json=engine).create()
        if result.href:
            return Engine(name).load()
        else:
            raise CreateEngineFailed('Could not create the engine, '
                                     'reason: {}'.format(result.msg))
'''
def virtual_resource_add(self, name, vfw_id, domain='Shared Domain',
                             show_master_nic=False):
        """ Master Engine only
        
        Add a virtual resource to this master engine
        
        :param name: name for virtual resource
        :param vfw_id: virtual fw ID, must be unique, indicates the virtual engine instance
        :param domain: Domain to place this virtual resource, default Shared
        :param show_master_nic: Show master NIC mapping in virtual engine interface view
        :return: SMCResult with href set if success, or msg set if failure
        """
        return SMCElement(href=self.__load_href('virtual_resources'),
                          json=VirtualResource(
                                name, vfw_id, 
                                domain=domain,
                                show_master_nic=show_master_nic).as_dict()).create()
'''
                                                       
class InternalGateway(object):
    """ 
    InternalGateway represents the engine side VPN configuration
    This defines settings such as setting VPN sites on protected
    networks and generating certificates.
    
    :ivar: href: location of this internal gateway 
    :param kwargs: key/values retrieved from engine settings
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def modify_attribute(self, **kwargs):
        for k, v in kwargs.iteritems():
            if k in self.__dict__:
                self.__dict__.update({k:v})
        result = get_element_etag(
                    find_link_by_name('self', self.link))
        return SMCElement(href=result.href,
                          etag=result.etag,
                          json=vars(self)).update()                         
    #TODO:
    def vpn_site(self):
        """
        :method: GET
        """
        return search.element_by_href_as_json(
                find_link_by_name('vpn_site', self.link))
    
    #TODO:
    def internal_endpoint(self):
        """
        :method: GET
        """
        return search.element_by_href_as_json(
                find_link_by_name('internal_endpoint', self.link))
    
    #TODO:
    def gateway_certificate(self):
        """
        :method: GET
        """
        return search.element_by_href_as_json(
                find_link_by_name('gateway_certificate', self.link))
    
    def gateway_certificate_request(self):
        """
        :method: GET
        """
        return search.element_by_href_as_json(
                find_link_by_name('gateway_certificate_request', self.link))    
    
    #TODO: 
    def generate_certificate(self):
        """
        :method: POST
        """
        return search.element_by_href_as_json(
                find_link_by_name('generate_certificate', self.link))
    
    @property
    def href(self):
        return find_link_by_name('self', self.link)
                    
    def __repr__(self):
        return "%s(%r)" % (self.__class__, 'name={}'.format(self.name))
