// swift-tools-version: 6.2
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "AirDeskNative",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "AirDeskNative", targets: ["AirDeskNative"]),
        .executable(name: "AirDeskChecks", targets: ["AirDeskChecks"]),
        .library(name: "AirDeskCore", targets: ["AirDeskCore"]),
    ],
    targets: [
        .target(
            name: "AirDeskCore"
        ),
        .executableTarget(
            name: "AirDeskNative",
            dependencies: ["AirDeskCore"]
        ),
        .executableTarget(
            name: "AirDeskChecks",
            dependencies: ["AirDeskCore"]
        ),
    ]
)
