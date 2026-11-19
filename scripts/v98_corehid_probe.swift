import Foundation
import CoreHID
let serial = CommandLine.arguments.count > 1 ? CommandLine.arguments[1].uppercased() : "41:42:DF:39:9A:BE"
let manager = HIDDeviceManager()
let criteria = HIDDeviceManager.DeviceMatchingCriteria(product: "V98", serialNumber: serial)
print("WAITING FOR V98"); fflush(stdout)
for try await event in await manager.monitorNotifications(matchingCriteria: [criteria]) {
    if case .deviceMatched(let reference) = event {
        guard let client = HIDDeviceClient(deviceReference: reference) else { print("CLIENT ERROR"); exit(1) }
        print("MATCHED product=\(String(describing: await client.product)) transport=\(String(describing: await client.transport))")
        print("READY"); fflush(stdout)
        for try await item in await client.monitorNotifications(reportIDsToMonitor: [HIDReportID.allReports], elementsToMonitor: []) {
            switch item {
            case .inputReport(let id, let data, _): print("REPORT id=\(String(describing: id)) data=\(data.map { String(format: "%02x", $0) }.joined())"); fflush(stdout)
            case .deviceRemoved: print("REMOVED"); exit(0)
            default: print("OTHER \(item)"); fflush(stdout)
            }
        }
    }
}
