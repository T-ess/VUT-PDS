#!/usr/bin/env python3

import subprocess
import sys
import os
import argparse
import csv

ip_src = 1
ip_dst = 2
port_src = 3
port_dst = 4
info_col = 5
bt_dht_bencoded_string = 6
bt_id = 7
bt_ip = 8
bt_port = 9

def call_tshark(filename, call):
    filename_csv = "./csv/{name}.csv".format(name=filename)
    file_out = open(filename_csv, "w")
    tshark_run = subprocess.call(call, shell=True, stdout=file_out, stderr=subprocess.STDOUT)
    if tshark_run != 0:
        error_msg = "Error: tshark call was unsuccessful. See csv/{name}.csv for further information.".format(name=filename)
        sys.exit(error_msg)

def init_flag():
    # get DNS queries for bootstrap nodes
    dns_bs_filters = "udp.srcport == 53 && (dns.qry.name contains dht || dns.qry.name contains router) && dns.resp.type == 1"
    dns_bs_call = "tshark -r {pcap} -T fields -E separator=';' -Y \"{filter}\" -e frame.time_relative -e dns.qry.name -e dns.a".format(pcap=args.pcap, filter=dns_bs_filters)
    call_tshark("dns_bootstrap", dns_bs_call)
    with open("./csv/dns_bootstrap.csv", newline='') as dns_bs_csv:
        ##TODO if empty, signatury nebo 8999
        reader = csv.reader(dns_bs_csv, delimiter=";")
        bootstrap_list = {}
        for rows in reader:
            ips = rows[2].split(",")
            for ip in ips:
                bootstrap_list[ip] = rows[1]

    # get BT-DHT initial requests to bootstrap nodes
    ## find out port used for BT-DHT from initial requests
    ips_list = str(list(bootstrap_list.keys()))
    ips_list = "{" + ips_list[1:len(ips_list)-1] + "}"
    ips_list = ips_list.replace("'", "\"")
    nodes_bs_filters = "ip.dst in {ips}".format(ips=ips_list)
    nodes_bs_call = "tshark -r {pcap} -T fields -E separator=';' -Y \"{filter}\" -e frame.time_relative -e udp.srcport".format(pcap=args.pcap, filter=nodes_bs_filters)
    call_tshark("nodes_bootstrap", nodes_bs_call)
    with open("./csv/nodes_bootstrap.csv", newline='') as node_bs_csv:
        reader = csv.reader(node_bs_csv, delimiter=";")
        try:
            row1 = next(reader)
        except:
            sys.exit("No data, possibly the BT-DHT bootstrapping communication is missing or was not detected.")
        dht_port = row1[1]
    ## get all BT-DHT communication as a csv file
    btdht_call = "tshark -r {pcap} -d udp.port=={port},bt-dht -T fields -E separator=';' -E header=y -e frame.time_relative -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e _ws.col.Info -e bt-dht.bencoded.string -e bt-dht.id -e bt-dht.ip -e bt-dht.port \"bt-dht\"".format(pcap=args.pcap, port=dht_port)
    call_tshark("bt_dht", btdht_call)

    # collect information about initial bootstrapping
    with open("./csv/bt_dht.csv", newline='') as btdht_csv:
        reader = csv.reader(btdht_csv, delimiter=";")
        for key in bootstrap_list.keys():
            req = False
            res = False
            btdht_csv.seek(0)
            for rows in reader:
                if req == False and rows[ip_dst] == key:
                    tID_index = rows[bt_dht_bencoded_string].find("t,")
                    if tID_index == -1:
                        sys.exit("Invalid BT-DHT packet.")
                    tID = rows[bt_dht_bencoded_string][tID_index+2:tID_index+6]
                    bootstrap_list[key] += "\n1 initial request sent to port {port}, transaction ID {id}\n".format(port=rows[port_dst], id=tID)
                    req = True
                    continue
                if req == True and tID in rows[bt_dht_bencoded_string]:
                    bootstrap_list[key] += "1 response received: {info}\n".format(info=rows[info_col])
                    res = True
                    break
            if req == False:
                bootstrap_list[key] += "\nno initial request sent\n"
            if req == True and res == False:
                bootstrap_list[key] += "no response received\n"
    for key in bootstrap_list.keys():
        print("{key} : {val}".format(key=key, val=bootstrap_list[key]))

def peer_flag():
    # get BT-DHT port number
    btdht_port_call = "tshark -r {pcap} -a packets:1 -T fields -Y \'udp contains \"get_peers\" || udp contains \"find_node\"\' -E separator=';' -e udp.srcport".format(pcap=args.pcap)
    try:
        dht_port_s = subprocess.check_output(btdht_port_call, shell=True)
    except subprocess.CalledProcessError as e:
        sys.exit("Error: tshark call was unsuccessful.")
    if not dht_port_s:
        sys.exit("Error: BT-DHT port not found. Possibly no BT-DHT requests in the input capture or TShark version is not 4.0.0 or higher.")
    dht_port = int(dht_port_s)
    # get all BT-DHT communication as a csv file
    btdht_call = "tshark -r {pcap} -d udp.port=={port},bt-dht -T fields -E separator=';' -E header=y -e frame.time_relative -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e _ws.col.Info -e bt-dht.bencoded.string -e bt-dht.id -e bt-dht.ip -e bt-dht.port \"bt-dht\"".format(pcap=args.pcap, port=dht_port)
    call_tshark("bt_dht", btdht_call)
    # get information about neighbours (filter responses only)
    nodes_list = {}
    with open("./csv/bt_dht.csv", newline='') as btdht_csv, open("./csv/bt_dht_nodes_peers.csv", "w", newline='') as btdht_csv_np:
        reader = csv.reader(btdht_csv, delimiter=";")
        try:
            responses_f = filter(lambda p: 'y,r' in p[bt_dht_bencoded_string], reader)
        except:
            sys.exit("Filtering of BT-DHT responses was unsuccessful, possibly the BT-DHT communication is missing or was not detected.")
        csv.writer(btdht_csv_np, delimiter=";").writerows(responses_f)
    with open("./csv/bt_dht_nodes_peers.csv", newline='') as btdht_csv_np:
        reader = csv.reader(btdht_csv_np, delimiter=";")
        for rows in reader:
            node_id_i = rows[bt_dht_bencoded_string].find("id,")
            node_id = rows[bt_dht_bencoded_string][node_id_i+3:node_id_i+43]
            if (node_id in nodes_list):
                nodes_list[node_id][2] += 1
            else:
                nodes_list[node_id] = list((rows[ip_src], rows[port_src], 1))
        for key in nodes_list.keys():
            print("Node ID {id}: {ip}:{port}, {conn} connection(s)".format(id=key, ip=nodes_list[key][0], port=nodes_list[key][1], conn=nodes_list[key][2]))

def download_flag():
    # get information about hash and peers from handshake
    handshake_call = "tshark -r {pcap} -T fields -E separator=';' -Y \"bittorrent.info_hash\" -o tcp.reassemble_out_of_order:TRUE -2 -e frame.time_relative -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport -e bittorrent.info_hash".format(pcap=args.pcap)
    call_tshark("handshakes", handshake_call)
    hash_list = {}
    with open("./csv/handshakes.csv", newline='') as handshakes_csv:
        reader = csv.reader(handshakes_csv, delimiter=";")
        ip = next(reader)[1]
        handshakes_csv.seek(0)
        for rows in reader:
            if rows[1] == ip:
                if rows[5] not in hash_list:
                    hash_list[rows[5]] = list()
                hash_list[rows[5]].append(rows[2])
            else:
                hash_list[rows[5]][hash_list[rows[5]].index(rows[1])] += ";1"
    ## remove handshakes without answer
    for key in hash_list:
        hash_list[key][:] = [x for x in hash_list[key] if (";1" in x)]
        for ip in hash_list[key]:
            hash_list[key][hash_list[key].index(ip)] = ip[:len(ip)-2]
    # filter Piece messages from the peers
    for file_hash in hash_list:
        file_size = 0
        ips_list = str(hash_list[file_hash])
        ips_list = "{" + ips_list[1:len(ips_list)-1] + "}"
        ips_list = ips_list.replace("'", "\"")
        pieces_filter = "bittorrent.msg.type == 7 and ip.src in {ips}".format(ips=ips_list)
        pieces_call = "tshark -r {pcap} -T fields -E separator=';' -Y \"{filter}\" -o tcp.reassemble_out_of_order:TRUE -2 -e frame.time_relative -e ip.src -e tcp.srcport -e bittorrent.piece.index -e bittorrent.msg.length".format(filter=pieces_filter, pcap=args.pcap)
        call_tshark(file_hash, pieces_call)
        pieces_dict = {}
        with open("./csv/{filehash}.csv".format(filehash=file_hash), newline='') as filehash_csv:
            reader = csv.reader(filehash_csv, delimiter=";")
            csv_empty = True
            for rows in reader:
                csv_empty = False
                for ind in rows[3].split(","):
                    if ind not in pieces_dict:
                        pieces_dict[ind] = list()
                    contributor = "{ip}:{port}".format(ip=rows[1], port=rows[2])
                    if contributor not in pieces_dict[ind]:
                        pieces_dict[ind].append(contributor)
            print("\ninfo_hash: {ih}".format(ih=file_hash))
            print("pieces and their contributors:")
            if csv_empty:
                print("No Pieces messages found for info_hash {ih}. Possibly UDP or an extension used.".format(ih=file_hash))
            else:
                for hsh, val in pieces_dict.items():
                    print("piece index " + hsh + ", contributors " + str(val))

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument('-pcap', type=str, required=True)
parser.add_argument('-init', action='store_true')
parser.add_argument('-peers', action='store_true')
parser.add_argument('-download', action='store_true')
args = parser.parse_args()

if args.init:
    init_flag()
if args.peers:
    peer_flag()
if args.download:
    download_flag()
