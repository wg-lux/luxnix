{
  nodes.node1.interfaces.lan.physicalConnections = [{ node = "node2"; interface = "wan"; }];
  networks.home = {
    name = "Home Network";
    cidrv4 = "192.168.1.0/24";
  };
}
