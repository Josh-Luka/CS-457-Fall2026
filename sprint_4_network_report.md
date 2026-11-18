# Sprint 4: Network Verification Report
**Author:** Luka [or your full name]  
**Date:** November 2026  
**Course/Sprint:** Sprint 4 - CML 1-Router Network Topology & Infrastructure Deployment  

---

## 1. Executive Summary
This report documents the deployment, configuration, and verification of the 1-router multi-subnet network topology inside Cisco Modeling Labs (CML). The architecture connects a single Cisco IOSv router (`JL-R1`) across three routed interfaces to Subnet A (`192.168.10.0/24` - `JL-Client1`), Subnet B (`192.168.11.0/24` - `JL-Client2`), and Subnet C (`192.168.20.0/24` - `JL-Server`). Router `JL-R1` provides inter-subnet routing, dynamic DHCP leases, authoritative DNS name resolution, and NAT overload (PAT) for external network connectivity.

---

## 2. Network Topology Diagram
<img width="288" height="452" alt="image" src="https://github.com/user-attachments/assets/4c0b7d85-88ba-469f-9a93-5930ac4b73a1" />

---

## 3. Router R1 Verification Outputs

### 3.1 Interface Status (`show ip interface brief`)
<img width="681" height="161" alt="image" src="https://github.com/user-attachments/assets/afb0f647-a900-4b73-9445-d7881d5d6d4c" />

### 3.2 Routing Table
<img width="568" height="245" alt="image" src="https://github.com/user-attachments/assets/f3d922fa-d938-4e98-a9d0-9932dca6b22c" />

### 3.3 DHCP Bindings
<img width="637" height="152" alt="image" src="https://github.com/user-attachments/assets/8094dfe7-f57d-4a42-b469-28e4bfb69f42" />

### 3.4 Host Table
<img width="587" height="229" alt="image" src="https://github.com/user-attachments/assets/b58358ab-c3bc-48b0-802c-06ea5c6965dd" />

---

## 4. Client & Server Verification Logs

### 4.1 Client 1
<img width="717" height="596" alt="image" src="https://github.com/user-attachments/assets/3a62b7f7-9215-4f6e-ac42-4d6c3706b942" />

### 4.2 Client 2
<img width="750" height="545" alt="image" src="https://github.com/user-attachments/assets/7b81f545-39a6-4bea-9abc-c1f1b4326bd2" />

---

## 5. Wireshark DNS Analysis

### 5.1 Annotated Wireshark Screenshot
<img width="951" height="547" alt="image" src="https://github.com/user-attachments/assets/ff93095b-d61e-4c5a-879f-d1f61b648922" />
Destination and source IP (Yellow), Protocol and Port (Green), DNS Standard Query (Blue), DNS Standard Response (Pink)

### 5.2 Packet Breakdown & Explination

#### Query Details: A DNS Standard Query was initiated from Client 1(192.168.10.2) to Router JL-R1 (192.168.10.1) requesting resolution for the fully qualified domain name server.luka.edu over UDP port 53

#### Response Details: Router JL-R1 acted as the authoritative DNS server and successully returned a Standard REsponce containing the static A-record pointing to the Games Server's IP address (192.168.20.100)
