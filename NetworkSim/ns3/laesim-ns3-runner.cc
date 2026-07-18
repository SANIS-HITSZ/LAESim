/*
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Interactive ns-3 message-level network runner for LAESim.
 */

#include "ns3/aodv-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/olsr-module.h"
#include "ns3/tag.h"
#include "ns3/yans-wifi-helper.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

using namespace ns3;

namespace
{
constexpr uint16_t kPort = 9000;

class PacketIdTag : public Tag
{
public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("ns3::LaesimPacketIdTag")
                                .SetParent<Tag>()
                                .AddConstructor<PacketIdTag>();
        return tid;
    }

    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }

    uint32_t GetSerializedSize() const override
    {
        return 1 + m_packetId.size();
    }

    void Serialize(TagBuffer buffer) const override
    {
        buffer.WriteU8(static_cast<uint8_t>(m_packetId.size()));
        buffer.Write(reinterpret_cast<const uint8_t*>(m_packetId.data()), m_packetId.size());
    }

    void Deserialize(TagBuffer buffer) override
    {
        const uint8_t size = buffer.ReadU8();
        std::vector<uint8_t> bytes(size);
        buffer.Read(bytes.data(), bytes.size());
        m_packetId.assign(bytes.begin(), bytes.end());
    }

    void Print(std::ostream& stream) const override
    {
        stream << m_packetId;
    }

    void SetPacketId(const std::string& packetId)
    {
        m_packetId = packetId;
    }

    const std::string& GetPacketId() const
    {
        return m_packetId;
    }

private:
    std::string m_packetId;
};

NS_OBJECT_ENSURE_REGISTERED(PacketIdTag);

NodeContainer g_nodes;
Ipv4InterfaceContainer g_interfaces;
std::vector<Ptr<Socket>> g_receivers;
std::vector<Ptr<Socket>> g_senders;
std::unordered_map<uint32_t, uint32_t> g_nodeIndex;
std::unordered_map<std::string, Time> g_sentAt;
uint64_t g_packetsSent = 0;
uint64_t g_packetsDelivered = 0;
uint64_t g_bytesDelivered = 0;
Time g_totalDelay;
Time g_packetTimeout;

bool IsValidPacketId(const std::string& packetId)
{
    if (packetId.empty() || packetId.size() > 128) {
        return false;
    }
    return std::all_of(packetId.begin(), packetId.end(), [](unsigned char value) {
        return std::isalnum(value) || value == '.' || value == '_' || value == ':' || value == '-';
    });
}

void ExpirePackets()
{
    std::vector<std::string> expired;
    for (const auto& [packetId, sentAt] : g_sentAt) {
        if (Simulator::Now() - sentAt >= g_packetTimeout) {
            expired.push_back(packetId);
        }
    }
    for (const std::string& packetId : expired) {
        g_sentAt.erase(packetId);
        std::cout << "DROP " << packetId << " timeout" << std::endl;
    }
}

void ReceivePacket(Ptr<Socket> socket)
{
    Address sender;
    while (Ptr<Packet> packet = socket->RecvFrom(sender)) {
        PacketIdTag packetIdTag;
        if (!packet->PeekPacketTag(packetIdTag)) {
            continue;
        }
        const std::string& packetId = packetIdTag.GetPacketId();

        const uint32_t nodeId = socket->GetNode()->GetId();
        const uint32_t nodeIndex = g_nodeIndex.at(nodeId);
        const auto sent = g_sentAt.find(packetId);
        if (sent != g_sentAt.end()) {
            g_totalDelay += Simulator::Now() - sent->second;
            g_sentAt.erase(sent);
        }

        ++g_packetsDelivered;
        g_bytesDelivered += packet->GetSize();
        std::cout << "DELIVER " << packetId << " " << nodeIndex << " " << packet->GetSize()
                  << " " << Simulator::Now().GetNanoSeconds() << std::endl;
    }
}

void PrintMetrics()
{
    const double elapsed = std::max(Simulator::Now().GetSeconds(), 1e-9);
    const double lossRate = g_packetsSent == 0
                                ? 0.0
                                : static_cast<double>(g_packetsSent - g_packetsDelivered) /
                                      static_cast<double>(g_packetsSent);
    const double throughputBps = static_cast<double>(g_bytesDelivered) * 8.0 / elapsed;
    const double averageDelayMs = g_packetsDelivered == 0
                                      ? 0.0
                                      : g_totalDelay.GetMilliSeconds() /
                                            static_cast<double>(g_packetsDelivered);

    std::cout << std::fixed << std::setprecision(6) << "METRICS " << g_packetsSent << " "
              << g_packetsDelivered << " " << lossRate << " " << throughputBps << " "
              << averageDelayMs << " " << Simulator::Now().GetNanoSeconds() << std::endl;
}

void ConfigureNetwork(uint32_t nodeCount,
                      const std::string& routing,
                      double maxRange,
                      double txPowerDbm,
                      double warmupSeconds,
                      double packetTimeoutSeconds)
{
    g_packetTimeout = Seconds(packetTimeoutSeconds);
    g_nodes.Create(nodeCount);

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211g);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("ErpOfdmRate6Mbps"),
                                 "ControlMode",
                                 StringValue("ErpOfdmRate6Mbps"));

    YansWifiChannelHelper channel = YansWifiChannelHelper::Default();
    channel.AddPropagationLoss("ns3::RangePropagationLossModel",
                               "MaxRange",
                               DoubleValue(maxRange));

    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(txPowerDbm));
    phy.Set("TxPowerEnd", DoubleValue(txPowerDbm));

    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, g_nodes);

    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(g_nodes);
    for (uint32_t i = 0; i < nodeCount; ++i) {
        g_nodes.Get(i)->GetObject<MobilityModel>()->SetPosition(Vector(i * 5.0, 0.0, 0.0));
    }

    InternetStackHelper internet;
    if (routing == "aodv") {
        AodvHelper aodv;
        internet.SetRoutingHelper(aodv);
    }
    else if (routing == "olsr") {
        OlsrHelper olsr;
        internet.SetRoutingHelper(olsr);
    }
    else {
        NS_FATAL_ERROR("Unsupported routing protocol: " << routing);
    }
    internet.Install(g_nodes);

    Ipv4AddressHelper ipv4;
    ipv4.SetBase("10.42.0.0", "255.255.255.0");
    g_interfaces = ipv4.Assign(devices);

    TypeId udpFactory = TypeId::LookupByName("ns3::UdpSocketFactory");
    for (uint32_t i = 0; i < nodeCount; ++i) {
        g_nodeIndex[g_nodes.Get(i)->GetId()] = i;

        Ptr<Socket> receiver = Socket::CreateSocket(g_nodes.Get(i), udpFactory);
        receiver->Bind(InetSocketAddress(Ipv4Address::GetAny(), kPort));
        receiver->SetRecvCallback(MakeCallback(&ReceivePacket));
        g_receivers.push_back(receiver);

        Ptr<Socket> sender = Socket::CreateSocket(g_nodes.Get(i), udpFactory);
        sender->Bind();
        g_senders.push_back(sender);
    }

    Simulator::Stop(Seconds(warmupSeconds));
    Simulator::Run();
    std::cout << "READY " << Simulator::Now().GetNanoSeconds() << std::endl;
}

bool HandleCommand(const std::string& line)
{
    std::istringstream input(line);
    std::string command;
    input >> command;

    if (command.empty()) {
        return true;
    }
    if (command == "POSE") {
        uint32_t node;
        double x;
        double y;
        double z;
        if (!(input >> node >> x >> y >> z) || node >= g_nodes.GetN()) {
            std::cout << "ERROR invalid POSE" << std::endl;
            return true;
        }
        g_nodes.Get(node)->GetObject<MobilityModel>()->SetPosition(Vector(x, y, z));
        return true;
    }
    if (command == "SEND") {
        uint32_t source;
        uint32_t destination;
        uint32_t sizeBytes;
        std::string packetId;
        if (!(input >> source >> destination >> sizeBytes >> packetId) ||
            source >= g_nodes.GetN() || destination >= g_nodes.GetN() ||
            sizeBytes == 0 || sizeBytes > 60000 || !IsValidPacketId(packetId)) {
            std::cout << "ERROR invalid SEND" << std::endl;
            return true;
        }

        Ptr<Packet> packet = Create<Packet>(sizeBytes);
        PacketIdTag packetIdTag;
        packetIdTag.SetPacketId(packetId);
        packet->AddPacketTag(packetIdTag);
        const int sent = g_senders[source]->SendTo(
            packet,
            0,
            InetSocketAddress(g_interfaces.GetAddress(destination), kPort));
        if (sent >= 0) {
            ++g_packetsSent;
            g_sentAt[packetId] = Simulator::Now();
            std::cout << "QUEUED " << packetId << " " << sent << std::endl;
        }
        else {
            std::cout << "DROP " << packetId << " socket" << std::endl;
        }
        return true;
    }
    if (command == "STEP") {
        double milliseconds;
        if (!(input >> milliseconds) || milliseconds <= 0.0) {
            std::cout << "ERROR invalid STEP" << std::endl;
            return true;
        }
        Simulator::Stop(MilliSeconds(milliseconds));
        Simulator::Run();
        ExpirePackets();
        std::cout << "STEP_DONE " << Simulator::Now().GetNanoSeconds() << std::endl;
        return true;
    }
    if (command == "METRICS") {
        PrintMetrics();
        return true;
    }
    if (command == "QUIT") {
        PrintMetrics();
        return false;
    }

    std::cout << "ERROR unknown command" << std::endl;
    return true;
}
} // namespace

int main(int argc, char* argv[])
{
    uint32_t nodeCount = 6;
    std::string routing = "olsr";
    double maxRange = 250.0;
    double txPowerDbm = 16.0;
    double warmupSeconds = 3.0;
    double packetTimeoutSeconds = 5.0;

    CommandLine cmd(__FILE__);
    cmd.AddValue("nodes", "Number of LAESim network nodes", nodeCount);
    cmd.AddValue("routing", "Routing protocol: olsr or aodv", routing);
    cmd.AddValue("maxRange", "Maximum radio range in meters", maxRange);
    cmd.AddValue("txPowerDbm", "Wi-Fi transmit power in dBm", txPowerDbm);
    cmd.AddValue("warmupSeconds", "Routing warmup duration", warmupSeconds);
    cmd.AddValue("packetTimeoutSeconds", "Drop-state timeout for undelivered packets", packetTimeoutSeconds);
    cmd.Parse(argc, argv);

    if (nodeCount == 0 || maxRange <= 0.0 || warmupSeconds < 0.0 || packetTimeoutSeconds <= 0.0) {
        NS_FATAL_ERROR("Invalid ns-3 runner configuration");
    }

    ConfigureNetwork(nodeCount,
                     routing,
                     maxRange,
                     txPowerDbm,
                     warmupSeconds,
                     packetTimeoutSeconds);

    std::string line;
    while (std::getline(std::cin, line) && HandleCommand(line)) {
    }

    Simulator::Destroy();
    return 0;
}
