# Network Architecture

## Overview
This document describes the network architecture of the LuxNix system, detailing how different components interact and how the network is structured for security and efficiency.

## Network Topology

### Basic Structure
- Primary network segment: 192.168.1.1/24 (Home network)
- System types:
  - Development workstations (gc-* series)
  - Server systems (s-* series)
  - Network services

### Core Components

#### Service Discovery
The system uses Avahi for local service discovery with the following features:
- mDNS/DNS-SD support enabled
- Workstation and service advertisement
- Address and domain publishing
- Hardware information broadcasting
- User service discovery

#### Network Optimization
Server configurations include several performance optimizations:
```nix
# TCP BBR for improved throughput and latency
boot.kernel.sysctl = {
  "net.core.default_qdisc" = "fq";
  "net.ipv4.tcp_congestion_control" = "bbr";
};
```

These settings provide:
- Improved congestion control using BBR
- Better throughput on high-latency networks
- Reduced bufferbloat through fair queuing

#### System Reliability
Network-critical systems implement watchdog services:
- Runtime watchdog: 20-second interval
- Reboot watchdog: 30-second timeout
- Automatic recovery from network-related failures

#### DNS Configuration
- Local DNS resolution through Avahi (nssmdns4)
- DNS utilities available on server systems
- Integrated with service discovery

## Security Considerations

### Server Hardening
Servers implement several security measures:
- Disabled password-based sudo access for wheel group
- Restricted sudo execution to wheel group members
- Minimal system with disabled documentation
- Immutable user configuration by default

### Network Service Protection
- Systematic service isolation
- Controlled service advertisement
- Protected local name resolution

## Deployment Configurations

### Server Role
Server systems are configured with:
- NFS utilities
- iSCSI support
- DNS tools
- Headless operation optimizations
- UTC timezone standardization

### Service Availability
- Network-dependent services have wait-online disabled
- Watchdog services ensure system availability
- Emergency mode disabled in favor of remote accessibility

## Network Interfaces

### Tailscale Integration
- Supported on various nodes (server-03, etc.)
- Integrated with home network segment
- Provides secure overlay networking

## Future Expansion
The current topology supports expansion through:
- Additional network segments
- New server nodes
- Extended service discovery
- Enhanced monitoring capabilities

## Monitoring Infrastructure

### Core Components
- **Prometheus**: Primary metrics collection and storage
  - Port: 3020
  - Node exporter enabled (Port: 3021)
  - System metrics collection
  - Home Assistant integration

- **Loki**: Log aggregation system
  - HTTP port: 3030
  - Local file storage configuration
  - Journal log collection

- **Grafana**: Visualization and dashboarding
  - Port: 3010
  - PostgreSQL backend
  - OAuth2 authentication integration
  - Automated datasource provisioning

- **Promtail**: Log forwarding agent
  - Port: 3031
  - Systemd journal integration
  - Automatic labeling

### Alerting System
- **AlertManager**: Alert handling and routing
  - Port: 9093
  - Webhook integration
  - Gotify notification support
  - Configurable grouping and timing

### Service Discovery and Access
All monitoring services are exposed through Traefik with:
- HTTPS enforcement
- Let's Encrypt certification
- Domain-based routing
- Load balancing configuration

### Data Flow
1. Metrics Collection:
   - Node exporter collects system metrics
   - Home Assistant provides application metrics
   - Prometheus scrapes and stores metrics

2. Log Collection:
   - Promtail collects system logs
   - Forwards to Loki for storage
   - Structured metadata support

3. Visualization:
   - Grafana connects to both Prometheus and Loki
   - Automated dashboard provisioning
   - Role-based access control

## VPN Infrastructure

### Core Configuration
- Main Domain: vpn.luxnix.org
- Backup DNS Servers:
  - 8.8.8.8 (Google)
  - 1.1.1.1 (Cloudflare)

### Features
- Optional Stage 1 Boot Integration
- Domain-based routing
- Redundant DNS configuration

### Network Integration
- Custom domain configuration
- Fallback name resolution
- Early boot availability option

## Security Considerations

### Authentication
- OAuth2 integration for Grafana
- Role-based access control
- Secure credential management through SOPS

### Network Security
- TLS encryption for all services
- VPN segregation
- Secure metrics collection

### Access Control
- Role-based authorization in Grafana
- Service-specific access controls
- Protected metrics endpoints

## Service Endpoints

### Monitoring Stack
```
grafana.homelab.haseebmajid.dev      -> Port 3010
prometheus.homelab.haseebmajid.dev    -> Port 3020
promtail.homelab.haseebmajid.dev     -> Port 3031
alertmanager.homelab.haseebmajid.dev  -> Port 9093
```

### VPN Services
```
vpn.luxnix.org    -> Primary VPN endpoint
```

## Deployment Guidelines

### Monitoring Stack Deployment
1. Ensure PostgreSQL database is configured
2. Configure SOPS secrets for:
   - Home Assistant token
   - OAuth2 credentials
3. Verify Traefik configuration
4. Deploy services in order:
   - Prometheus and exporters
   - Loki and Promtail
   - Grafana
   - AlertManager

### VPN Deployment
1. Configure domain settings
2. Verify DNS resolver configuration
3. Optional: Enable stage-1 boot integration
4. Validate network connectivity

## Troubleshooting

### Monitoring Issues
1. Metrics Collection
   - Verify Prometheus targets
   - Check node exporter status
   - Validate scrape configurations

2. Log Collection
   - Check Promtail status
   - Verify Loki ingestion
   - Review journal collection

3. Visualization
   - Verify Grafana datasource connectivity
   - Check OAuth2 configuration
   - Validate role mappings

### VPN Issues
1. Connection Problems
   - Verify DNS resolution
   - Check nameserver availability
   - Validate domain configuration

2. Boot Integration
   - Verify stage-1 configuration
   - Check network availability
   - Validate DNS settings

## Best Practices

### Monitoring
1. Regular backup of Grafana dashboards
2. Monitor alert notification channels
3. Regular review of log retention policies
4. Performance optimization of metrics collection

### VPN
1. Maintain backup DNS servers
2. Regular connectivity testing
3. Monitor VPN service logs
4. Review access patterns


## Troubleshooting

### Common Issues
1. Service Discovery Problems
   - Verify Avahi service status
   - Check mDNS resolution
   - Confirm network segment connectivity

2. Network Performance
   - Verify BBR configuration
   - Check network interface status
   - Monitor system watchdog logs

3. System Availability
   - Review watchdog logs
   - Check network service status
   - Verify DNS resolution

## Technical Reference

### Key Configuration Files
- `/modules/nixos/services/avahi/default.nix`: Service discovery
- `topology.nix`: Network topology definition
- Server role configuration: Network optimization and security settings

### Required Packages
```nix
environment.systemPackages = [
  pkgs.nfs-utils
  pkgs.openiscsi
  pkgs.dnsutils
];
```

### Network Parameters
- Default network: 192.168.1.1/24
- Service discovery: Enabled
- TCP congestion control: BBR
- Queue discipline: FQ (Fair Queuing)