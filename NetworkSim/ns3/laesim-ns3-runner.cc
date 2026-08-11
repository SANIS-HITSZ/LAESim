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
#include <cmath>
#include <cstdint>
#include <queue>
#include <iomanip>
#include <iostream>
#include <limits>
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
struct PendingPacket
{
    Time sentAt;
    uint32_t source;
    uint32_t destination;
    uint32_t sizeBytes = 0;
    bool logical = false;
    std::string linkType = "wifi";
    int64_t propagationDelayNs = 0;
    int64_t serializationDelayNs = 0;
    double dataRateBps = 0.0;
    double packetErrorRate = 0.0;
    std::string failureReason;
    double trueRangeM = 0.0;
    double fsplDb = 0.0;
    double rxPowerDbm = 0.0;
    double snrDb = 0.0;
    double frequencyHz = 0.0;
    double bandwidthHz = 0.0;
    uint32_t routeHopCount = 0;
    std::string routeNodes;
};
std::unordered_map<std::string, PendingPacket> g_pendingPackets;
uint64_t g_packetsSent = 0;
uint64_t g_packetsDelivered = 0;
uint64_t g_bytesDelivered = 0;
Time g_totalDelay;
Time g_packetTimeout;
double g_maxRange = 0.0;
std::string g_routing;
std::unordered_map<uint64_t, Time> g_logicalLinkAvailableAt;
Ptr<UniformRandomVariable> g_random;

bool IsValidPacketId(const std::string& packetId)
{
    if (packetId.empty() || packetId.size() > 128) {
        return false;
    }
    return std::all_of(packetId.begin(), packetId.end(), [](unsigned char value) {
        return std::isalnum(value) || value == '.' || value == '_' || value == ':' || value == '-';
    });
}

int32_t FindTopologyHopCount(uint32_t source, uint32_t destination)
{
    std::vector<int32_t> hops(g_nodes.GetN(), -1);
    std::queue<uint32_t> pending;
    hops[source] = 0;
    pending.push(source);
    while (!pending.empty()) {
        const uint32_t current = pending.front();
        pending.pop();
        if (current == destination) {
            return hops[current];
        }
        const Vector currentPosition =
            g_nodes.Get(current)->GetObject<MobilityModel>()->GetPosition();
        for (uint32_t candidate = 0; candidate < g_nodes.GetN(); ++candidate) {
            if (hops[candidate] >= 0 || candidate == current) {
                continue;
            }
            const Vector candidatePosition =
                g_nodes.Get(candidate)->GetObject<MobilityModel>()->GetPosition();
            if (CalculateDistance(currentPosition, candidatePosition) <= g_maxRange) {
                hops[candidate] = hops[current] + 1;
                pending.push(candidate);
            }
        }
    }
    return -1;
}

bool HasIpv4Route(uint32_t source, uint32_t destination)
{
    Ptr<Ipv4> ipv4 = g_nodes.Get(source)->GetObject<Ipv4>();
    Ptr<Ipv4RoutingProtocol> routing = ipv4->GetRoutingProtocol();
    Ipv4Header header;
    header.SetSource(g_interfaces.GetAddress(source));
    header.SetDestination(g_interfaces.GetAddress(destination));
    Socket::SocketErrno socketError = Socket::ERROR_NOTERROR;
    return routing->RouteOutput(Create<Packet>(), header, nullptr, socketError) != nullptr;
}

void EmitDrop(const std::string& packetId,
              const std::string& reason,
              const PendingPacket& pending)
{
    const Vector sourcePosition =
        g_nodes.Get(pending.source)->GetObject<MobilityModel>()->GetPosition();
    const Vector destinationPosition =
        g_nodes.Get(pending.destination)->GetObject<MobilityModel>()->GetPosition();
    const double distance = CalculateDistance(sourcePosition, destinationPosition);
    const int32_t hopCount = FindTopologyHopCount(pending.source, pending.destination);
    const bool routeAvailable = HasIpv4Route(pending.source, pending.destination);
    const Time age = Simulator::Now() - pending.sentAt;

    std::cout << std::fixed << std::setprecision(6) << "DROP " << packetId << " " << reason
              << " " << Simulator::Now().GetNanoSeconds() << " " << age.GetNanoSeconds()
              << " " << pending.source << " " << pending.destination << " " << distance
              << " " << hopCount << " " << (routeAvailable ? 1 : 0) << " " << g_routing
              << " " << g_maxRange << " " << sourcePosition.x << " " << sourcePosition.y
              << " " << sourcePosition.z << " " << destinationPosition.x << " "
              << destinationPosition.y << " " << destinationPosition.z;
    if (pending.logical) {
        std::cout << " " << pending.linkType << " " << pending.propagationDelayNs << " "
                  << pending.serializationDelayNs << " " << pending.dataRateBps << " "
                  << pending.packetErrorRate << " " << pending.trueRangeM << " "
                  << pending.fsplDb << " " << pending.rxPowerDbm << " " << pending.snrDb
                  << " " << pending.frequencyHz << " " << pending.bandwidthHz;
        if (pending.routeHopCount > 0) {
            std::cout << " " << pending.routeHopCount << " " << pending.routeNodes;
        }
    }
    std::cout << std::endl;
}

void CompleteLogicalPacket(const std::string& packetId)
{
    const auto found = g_pendingPackets.find(packetId);
    if (found == g_pendingPackets.end()) {
        return;
    }
    const PendingPacket pending = found->second;
    g_pendingPackets.erase(found);

    if (g_random->GetValue() < pending.packetErrorRate) {
        EmitDrop(packetId, pending.failureReason, pending);
        return;
    }

    const Time delay = Simulator::Now() - pending.sentAt;
    g_totalDelay += delay;
    ++g_packetsDelivered;
    g_bytesDelivered += pending.sizeBytes;
    std::cout << std::fixed << std::setprecision(6) << "DELIVER " << packetId << " "
              << pending.destination << " " << pending.sizeBytes << " "
              << Simulator::Now().GetNanoSeconds() << " " << delay.GetNanoSeconds()
              << " " << pending.linkType << " " << pending.propagationDelayNs << " "
              << pending.serializationDelayNs << " " << pending.dataRateBps << " "
              << pending.packetErrorRate << " " << pending.trueRangeM << " "
              << pending.fsplDb << " " << pending.rxPowerDbm << " " << pending.snrDb
              << " " << pending.frequencyHz << " " << pending.bandwidthHz;
    if (pending.routeHopCount > 0) {
        std::cout << " " << pending.routeHopCount << " " << pending.routeNodes;
    }
    std::cout << std::endl;
}

void ExpirePackets()
{
    std::vector<std::string> expired;
    for (const auto& [packetId, pending] : g_pendingPackets) {
        if (Simulator::Now() - pending.sentAt >= g_packetTimeout) {
            expired.push_back(packetId);
        }
    }
    for (const std::string& packetId : expired) {
        const PendingPacket pending = g_pendingPackets.at(packetId);
        const int32_t hopCount = FindTopologyHopCount(pending.source, pending.destination);
        const bool routeAvailable = HasIpv4Route(pending.source, pending.destination);
        const std::string reason = pending.logical
                                       ? "timeout"
                                       : (hopCount < 0 ? "range"
                                                       : (!routeAvailable ? "routing" : "timeout"));
        g_pendingPackets.erase(packetId);
        EmitDrop(packetId, reason, pending);
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
        const auto sent = g_pendingPackets.find(packetId);
        Time delay;
        if (sent != g_pendingPackets.end()) {
            delay = Simulator::Now() - sent->second.sentAt;
            g_totalDelay += delay;
            g_pendingPackets.erase(sent);
        }

        ++g_packetsDelivered;
        g_bytesDelivered += packet->GetSize();
        std::cout << "DELIVER " << packetId << " " << nodeIndex << " " << packet->GetSize()
                  << " " << Simulator::Now().GetNanoSeconds() << " "
                  << delay.GetNanoSeconds() << std::endl;
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
    g_maxRange = maxRange;
    g_routing = routing;
    g_random = CreateObject<UniformRandomVariable>();
    g_random->SetStream(7);
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
        PendingPacket pending;
        pending.sentAt = Simulator::Now();
        pending.source = source;
        pending.destination = destination;
        pending.sizeBytes = sizeBytes;
        g_pendingPackets[packetId] = pending;
        ++g_packetsSent;
        const int sent = g_senders[source]->SendTo(
            packet,
            0,
            InetSocketAddress(g_interfaces.GetAddress(destination), kPort));
        if (sent >= 0) {
            std::cout << "QUEUED " << packetId << " " << sent << std::endl;
        }
        else {
            g_pendingPackets.erase(packetId);
            const int32_t hopCount = FindTopologyHopCount(source, destination);
            const bool routeAvailable = HasIpv4Route(source, destination);
            const std::string reason = hopCount < 0 ? "range" : (!routeAvailable ? "routing" : "socket");
            EmitDrop(packetId, reason, pending);
        }
        return true;
    }
    if (command == "LOGICAL_SEND") {
        uint32_t source;
        uint32_t destination;
        uint32_t sizeBytes;
        std::string packetId;
        int64_t propagationDelayNs;
        double dataRateBps;
        double packetErrorRate;
        std::string failureReason;
        double trueRangeM;
        double fsplDb;
        double rxPowerDbm;
        double snrDb;
        double frequencyHz;
        double bandwidthHz;
        if (!(input >> source >> destination >> sizeBytes >> packetId >> propagationDelayNs >>
              dataRateBps >> packetErrorRate >> failureReason >> trueRangeM >> fsplDb >>
              rxPowerDbm >> snrDb >> frequencyHz >> bandwidthHz) ||
            source >= g_nodes.GetN() || destination >= g_nodes.GetN() || sizeBytes == 0 ||
            sizeBytes > 60000 || !IsValidPacketId(packetId) || propagationDelayNs < 0 ||
            !std::isfinite(dataRateBps) || dataRateBps <= 0.0 ||
            !std::isfinite(packetErrorRate) || packetErrorRate < 0.0 ||
            packetErrorRate > 1.0 ||
            (failureReason != "link_error" && failureReason != "link_budget") ||
            !std::isfinite(trueRangeM) || trueRangeM <= 0.0 ||
            !std::isfinite(fsplDb) || !std::isfinite(rxPowerDbm) ||
            !std::isfinite(snrDb) || !std::isfinite(frequencyHz) || frequencyHz <= 0.0 ||
            !std::isfinite(bandwidthHz) || bandwidthHz <= 0.0) {
            std::cout << "ERROR invalid LOGICAL_SEND" << std::endl;
            return true;
        }

        const int64_t serializationDelayNs = std::max<int64_t>(
            1,
            static_cast<int64_t>(
                std::ceil(static_cast<double>(sizeBytes) * 8.0e9 / dataRateBps)));
        const uint64_t linkKey = (static_cast<uint64_t>(source) << 32) | destination;
        const Time transmissionStart = std::max(Simulator::Now(), g_logicalLinkAvailableAt[linkKey]);
        const Time transmissionFinish = transmissionStart + NanoSeconds(serializationDelayNs);
        const Time deliveryTime = transmissionFinish + NanoSeconds(propagationDelayNs);
        g_logicalLinkAvailableAt[linkKey] = transmissionFinish;

        PendingPacket pending;
        pending.sentAt = Simulator::Now();
        pending.source = source;
        pending.destination = destination;
        pending.sizeBytes = sizeBytes;
        pending.logical = true;
        pending.linkType = "satellite";
        pending.propagationDelayNs = propagationDelayNs;
        pending.serializationDelayNs = serializationDelayNs;
        pending.dataRateBps = dataRateBps;
        pending.packetErrorRate = packetErrorRate;
        pending.failureReason = failureReason;
        pending.trueRangeM = trueRangeM;
        pending.fsplDb = fsplDb;
        pending.rxPowerDbm = rxPowerDbm;
        pending.snrDb = snrDb;
        pending.frequencyHz = frequencyHz;
        pending.bandwidthHz = bandwidthHz;
        g_pendingPackets[packetId] = pending;
        ++g_packetsSent;
        Simulator::Schedule(deliveryTime - Simulator::Now(), &CompleteLogicalPacket, packetId);
        std::cout << "QUEUED " << packetId << " " << sizeBytes << std::endl;
        return true;
    }
    if (command == "LOGICAL_ROUTE") {
        uint32_t source;
        uint32_t destination;
        uint32_t sizeBytes;
        std::string packetId;
        uint32_t hopCount;
        if (!(input >> source >> destination >> sizeBytes >> packetId >> hopCount) ||
            source >= g_nodes.GetN() || destination >= g_nodes.GetN() ||
            sizeBytes == 0 || sizeBytes > 60000 || !IsValidPacketId(packetId) ||
            hopCount == 0 || hopCount >= g_nodes.GetN()) {
            std::cout << "ERROR invalid LOGICAL_ROUTE" << std::endl;
            return true;
        }

        Time routeCursor = Simulator::Now();
        int64_t totalPropagationDelayNs = 0;
        int64_t totalSerializationDelayNs = 0;
        double successProbability = 1.0;
        double minimumDataRateBps = std::numeric_limits<double>::infinity();
        double totalRangeM = 0.0;
        double worstFsplDb = -std::numeric_limits<double>::infinity();
        double worstRxPowerDbm = std::numeric_limits<double>::infinity();
        double worstSnrDb = std::numeric_limits<double>::infinity();
        double routeFrequencyHz = 0.0;
        double minimumBandwidthHz = std::numeric_limits<double>::infinity();
        std::string routeFailureReason = "link_error";
        std::vector<uint32_t> route;
        route.push_back(source);
        uint32_t previousDestination = source;

        for (uint32_t hop = 0; hop < hopCount; ++hop) {
            uint32_t hopSource;
            uint32_t hopDestination;
            int64_t propagationDelayNs;
            double dataRateBps;
            double packetErrorRate;
            std::string failureReason;
            double trueRangeM;
            double fsplDb;
            double rxPowerDbm;
            double snrDb;
            double frequencyHz;
            double bandwidthHz;
            if (!(input >> hopSource >> hopDestination >> propagationDelayNs >>
                  dataRateBps >> packetErrorRate >> failureReason >> trueRangeM >>
                  fsplDb >> rxPowerDbm >> snrDb >> frequencyHz >> bandwidthHz) ||
                hopSource >= g_nodes.GetN() || hopDestination >= g_nodes.GetN() ||
                hopSource != previousDestination || hopSource == hopDestination ||
                propagationDelayNs < 0 || !std::isfinite(dataRateBps) ||
                dataRateBps <= 0.0 || !std::isfinite(packetErrorRate) ||
                packetErrorRate < 0.0 || packetErrorRate > 1.0 ||
                (failureReason != "link_error" && failureReason != "link_budget") ||
                !std::isfinite(trueRangeM) || trueRangeM <= 0.0 ||
                !std::isfinite(fsplDb) || !std::isfinite(rxPowerDbm) ||
                !std::isfinite(snrDb) || !std::isfinite(frequencyHz) ||
                frequencyHz <= 0.0 || !std::isfinite(bandwidthHz) ||
                bandwidthHz <= 0.0) {
                std::cout << "ERROR invalid LOGICAL_ROUTE" << std::endl;
                return true;
            }

            const int64_t serializationDelayNs = std::max<int64_t>(
                1,
                static_cast<int64_t>(
                    std::ceil(static_cast<double>(sizeBytes) * 8.0e9 / dataRateBps)));
            const uint64_t linkKey =
                (static_cast<uint64_t>(hopSource) << 32) | hopDestination;
            const Time transmissionStart =
                std::max(routeCursor, g_logicalLinkAvailableAt[linkKey]);
            const Time transmissionFinish =
                transmissionStart + NanoSeconds(serializationDelayNs);
            routeCursor = transmissionFinish + NanoSeconds(propagationDelayNs);
            g_logicalLinkAvailableAt[linkKey] = transmissionFinish;

            totalPropagationDelayNs += propagationDelayNs;
            totalSerializationDelayNs += serializationDelayNs;
            successProbability *= 1.0 - packetErrorRate;
            minimumDataRateBps = std::min(minimumDataRateBps, dataRateBps);
            totalRangeM += trueRangeM;
            worstFsplDb = std::max(worstFsplDb, fsplDb);
            worstRxPowerDbm = std::min(worstRxPowerDbm, rxPowerDbm);
            worstSnrDb = std::min(worstSnrDb, snrDb);
            routeFrequencyHz = hop == 0 ? frequencyHz : routeFrequencyHz;
            minimumBandwidthHz = std::min(minimumBandwidthHz, bandwidthHz);
            if (packetErrorRate >= 1.0 && failureReason == "link_budget") {
                routeFailureReason = "link_budget";
            }
            previousDestination = hopDestination;
            route.push_back(hopDestination);
        }
        if (previousDestination != destination) {
            std::cout << "ERROR invalid LOGICAL_ROUTE" << std::endl;
            return true;
        }

        std::ostringstream routeStream;
        for (uint32_t index = 0; index < route.size(); ++index) {
            if (index > 0) {
                routeStream << ",";
            }
            routeStream << route[index];
        }

        PendingPacket pending;
        pending.sentAt = Simulator::Now();
        pending.source = source;
        pending.destination = destination;
        pending.sizeBytes = sizeBytes;
        pending.logical = true;
        pending.linkType = "satellite_route";
        pending.propagationDelayNs = totalPropagationDelayNs;
        pending.serializationDelayNs = totalSerializationDelayNs;
        pending.dataRateBps = minimumDataRateBps;
        pending.packetErrorRate = 1.0 - successProbability;
        pending.failureReason = routeFailureReason;
        pending.trueRangeM = totalRangeM;
        pending.fsplDb = worstFsplDb;
        pending.rxPowerDbm = worstRxPowerDbm;
        pending.snrDb = worstSnrDb;
        pending.frequencyHz = routeFrequencyHz;
        pending.bandwidthHz = minimumBandwidthHz;
        pending.routeHopCount = hopCount;
        pending.routeNodes = routeStream.str();
        g_pendingPackets[packetId] = pending;
        ++g_packetsSent;
        Simulator::Schedule(routeCursor - Simulator::Now(), &CompleteLogicalPacket, packetId);
        std::cout << "QUEUED " << packetId << " " << sizeBytes << std::endl;
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
