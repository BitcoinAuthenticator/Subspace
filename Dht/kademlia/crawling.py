from collections import Counter

from kademlia.log import Logger
from kademlia.utils import deferredDict
from kademlia.node import Node, NodeHeap


class SpiderCrawl(object):
    """
    Crawl the network and look for given 160-bit keys.
    """
    def __init__(self, protocol, node, peers, ksize, alpha):
        """
        Create a new C{SpiderCrawl}er.

        Args:
            protocol: A :class:`~kademlia.protocol.KademliaProtocol` instance.
            node: A :class:`~kademlia.node.Node` representing the key we're looking for
            peers: A list of :class:`~kademlia.node.Node` instances that provide the entry point for the network
            ksize: The value for k based on the paper
            alpha: The value for alpha based on the paper
        """
        self.protocol = protocol
        self.ksize = ksize
        self.alpha = alpha
        self.node = node
        self.nearest = NodeHeap(self.node, self.ksize)
        self.lastIDsCrawled = []
        self.log = Logger(system=self)
        self.log.info("creating spider with peers: %s" % peers)
        self.nearest.push(peers)


    def _find(self, rpcmethod):
        """
        Get either a value or list of nodes.

        Args:
            rpcmethod: The protocol's callfindValue or callFindNode.

        The process:
          1. calls find_* to current ALPHA nearest not already queried nodes,
             adding results to current nearest list of k nodes.
          2. current nearest list needs to keep track of who has been queried already
             sort by nearest, keep KSIZE
          3. if list is same as last time, next call should be to everyone not
             yet queried
          4. repeat, unless nearest list has all been queried, then ur done
        """
        self.log.info("crawling with nearest: %s" % str(tuple(self.nearest)))
        count = self.alpha
        if self.nearest.getIDs() == self.lastIDsCrawled:
            self.log.info("last iteration same as current - checking all in list now")
            count = len(self.nearest)
        self.lastIDsCrawled = self.nearest.getIDs()

        ds = {}
        for peer in self.nearest.getUncontacted()[:count]:
            ds[peer.id] = rpcmethod(peer, self.node)
            self.nearest.markContacted(peer)
        return deferredDict(ds).addCallback(self._nodesFound)

class RangeSpiderCrawl(SpiderCrawl):
    def __init__(self, protocol, prefix, lowest_node, highest_node, peers, ksize, alpha):
        SpiderCrawl.__init__(self, protocol, lowest_node, peers, ksize, alpha)
        self.prefix = prefix
        self.lowest_node = lowest_node
        self.highest_node = highest_node
        self.get_more_nodes = True
        self.nodesToQuery = NodeHeap(self.lowest_node, 1000000)
        self.nodesToQuery.push(peers)
        self.foundValues = []
        self.lastNodesQueried = []


    def find(self):
        """
        Find either the closest nodes or the value requested.
        """
        if self.get_more_nodes:
            return self._find(self.protocol.callFindNode)
        else:
            self.log.info("crawling with nearest: %s" % str(tuple(self.nodesToQuery)))
            count = self.alpha
            if self.nodesToQuery.getIDs() == self.lastNodesQueried:
                self.log.info("last iteration same as current - checking all in list now")
                count = len(self.nearest)
            self.lastNodesQueried = self.nodesToQuery.getIDs()
            ds = {}
            for peer in self.nodesToQuery.getUncontacted()[:count]:
                ds[peer.id] = self.protocol.callFindRange(peer, self.prefix)
                self.nodesToQuery.markContacted(peer)
        return deferredDict(ds).addCallback(self._nodesFound)

    def _nodesFound(self, responses):
        """
        Handle the result of an iteration in _find.
        """
        if self.get_more_nodes:
            toremove = []
            for peerid, response in responses.items():
                response = RPCFindResponse(response)
                if not response.happened():
                    toremove.append(peerid)
                else:
                    self.nearest.push(response.getNodeList())
                    self.nodesToQuery.push(response.getNodeList())
            self.nearest.remove(toremove)
            self.nodesToQuery.remove(toremove)
            self.get_more_nodes = False
            return self.find()
        else:
            toremove = []
            for peerid, response in responses.items():
                response = RPCFindResponse(response)
                if not response.happened():
                    toremove.append(peerid)
                else:
                    values = response.getValues()
                    if values is not None:
                        for value in values:
                            self.foundValues.append(value)
                        neighbors = response.getNeighbors()
                        for neighbor in neighbors:
                            n = Node(neighbor[0], neighbor[1], neighbor[2])
                            self.nodesToQuery.push(n)
            if self.nodesToQuery.allBeenContacted() and len(self.foundValues) == 0:
                return None
            elif self.nodesToQuery.allBeenContacted():
                return self._handleFoundValues(self.foundValues)
            self.nodesToQuery.remove(toremove)
            temp = self.nodesToQuery.getUncontacted()
            for node in temp:
                self.nodesToQuery.push(node)
                if self.highest_node > node.id > self.lowest_node.id:
                    self.lowest_node = node
            self.nodesToQuery = NodeHeap(self.lowest_node, 1000000)
            for node in temp:
                self.nodesToQuery.push(node)
            return self.find()



    def _handleFoundValues(self, values):
        """
        We got some values!  Exciting.  Let's remove duplicates
        from our list before returning.
        """
        ret = []
        for value in values:
            if value not in ret:
                ret.append(value)
        return ret



class ValueSpiderCrawl(SpiderCrawl):
    def __init__(self, protocol, node, peers, ksize, alpha):
        SpiderCrawl.__init__(self, protocol, node, peers, ksize, alpha)
        # keep track of the single nearest node without value - per
        # section 2.3 so we can set the key there if found
        self.nearestWithoutValue = NodeHeap(self.node, 1)

    def find(self):
        """
        Find either the closest nodes or the value requested.
        """
        return self._find(self.protocol.callFindValue)

    def _nodesFound(self, responses):
        """
        Handle the result of an iteration in _find.
        """
        toremove = []
        foundValues = []
        for peerid, response in responses.items():
            response = RPCFindResponse(response)
            if not response.happened():
                toremove.append(peerid)
            elif response.hasValue():
                foundValues.append(response.getValue())
            else:
                peer = self.nearest.getNodeById(peerid)
                self.nearestWithoutValue.push(peer)
                self.nearest.push(response.getNodeList())
        self.nearest.remove(toremove)

        if len(foundValues) > 0:
            return self._handleFoundValues(foundValues)
        if self.nearest.allBeenContacted():
            # not found!
            return None
        return self.find()

    def _handleFoundValues(self, values):
        """
        We got some values!  Exciting.  But let's make sure
        they're all the same or freak out a little bit.  Also,
        make sure we tell the nearest node that *didn't* have
        the value to store it.
        """
        valueCounts = Counter(values)
        if len(valueCounts) != 1:
            args = (self.node.long_id, str(values))
            self.log.warning("Got multiple values for key %i: %s" % args)
        value = valueCounts.most_common(1)[0][0]

        peerToSaveTo = self.nearestWithoutValue.popleft()
        if peerToSaveTo is not None:
            d = self.protocol.callStore(peerToSaveTo, self.node.id, value)
            return d.addCallback(lambda _: value)
        return value


class NodeSpiderCrawl(SpiderCrawl):
    def find(self):
        """
        Find the closest nodes.
        """
        return self._find(self.protocol.callFindNode)

    def _nodesFound(self, responses):
        """
        Handle the result of an iteration in _find.
        """
        toremove = []
        for peerid, response in responses.items():
            response = RPCFindResponse(response)
            if not response.happened():
                toremove.append(peerid)
            else:
                self.nearest.push(response.getNodeList())
        self.nearest.remove(toremove)

        if self.nearest.allBeenContacted():
            return list(self.nearest)
        return self.find()


class RPCFindResponse(object):
    def __init__(self, response):
        """
        A wrapper for the result of a RPC find.

        Args:
            response: This will be a tuple of (<response received>, <value>)
                      where <value> will be a list of tuples if not found or
                      a dictionary of {'value': v} where v is the value desired
        """
        self.response = response

    def happened(self):
        """
        Did the other host actually respond?
        """
        return self.response[0]

    def hasValue(self):
        return isinstance(self.response[1], dict)

    def getValue(self):
        return self.response[1]['value']

    def getValues(self):
        return self.response[1]['values']

    def getNeighbors(self):
        return self.response[1]['neighbors']

    def getNodeList(self):
        """
        Get the node list in the response.  If there's no value, this should
        be set.
        """
        nodelist = self.response[1] or []
        return [Node(*nodeple) for nodeple in nodelist]
