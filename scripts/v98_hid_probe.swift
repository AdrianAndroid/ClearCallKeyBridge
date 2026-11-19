import Foundation
import IOKit.hid
let serial = CommandLine.arguments.count > 1 ? CommandLine.arguments[1].uppercased() : "41:42:DF:39:9A:BE"
let m = IOHIDManagerCreate(kCFAllocatorDefault, 0)
IOHIDManagerSetDeviceMatching(m, [kIOHIDProductKey:"V98", kIOHIDSerialNumberKey:serial, kIOHIDTransportKey:"Bluetooth"] as CFDictionary)
let status = IOHIDManagerOpen(m, 0)
let set = IOHIDManagerCopyDevices(m) as? Set<IOHIDDevice> ?? []
print("ACCESS \(IOHIDCheckAccess(kIOHIDRequestTypeListenEvent).rawValue) MANAGER \(status) DEVICES \(set.count)"); fflush(stdout)
guard status == 0, set.count == 1, let d = set.first else { exit(2) }
let buf = UnsafeMutablePointer<UInt8>.allocate(capacity: 1024)
IOHIDDeviceRegisterInputValueCallback(d, { _, result, _, value in
 let e = IOHIDValueGetElement(value)
 print("VALUE status=\(result) page=\(IOHIDElementGetUsagePage(e)) usage=\(IOHIDElementGetUsage(e)) value=\(IOHIDValueGetIntegerValue(value))"); fflush(stdout)
}, nil)
IOHIDDeviceRegisterInputReportCallback(d, buf, 1024, { _, result, _, _, id, report, length in
 print("REPORT status=\(result) id=\(id) bytes=\((0..<length).map { String(format: "%02x",report[$0]) }.joined())"); fflush(stdout)
}, nil)
IOHIDDeviceScheduleWithRunLoop(d, CFRunLoopGetCurrent(), CFRunLoopMode.defaultMode.rawValue)
let opened = IOHIDDeviceOpen(d, 0)
print("DEVICE_OPEN \(opened)"); fflush(stdout)
if opened != 0 { exit(3) }
print("READY 90s"); fflush(stdout)
CFRunLoopRunInMode(CFRunLoopMode.defaultMode, 90, false)
IOHIDDeviceClose(d, 0)
IOHIDManagerClose(m, 0)
buf.deallocate()
print("DONE")
