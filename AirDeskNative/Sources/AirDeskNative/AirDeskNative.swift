import AVFoundation
import AirDeskCore
import CoreMedia
@preconcurrency import ApplicationServices
import AppKit
import Darwin

@main
@MainActor
final class AirDeskNativeApp: NSObject, NSApplicationDelegate, CameraManagerDelegate, VisionTrackerDelegate {
    
    let cameraManager = CameraManager()
    let visionTracker = VisionTracker()
    let gestureEngine = GestureEngine()
    let mouseController: MouseController
    let overlayWindowManager = OverlayWindowManager()
    private let options: CommandLineOptions
    private var localKeyMonitor: Any?
    private var globalKeyMonitor: Any?
    private var accessibilityTrusted = false

    init(options: CommandLineOptions) {
        self.options = options
        self.mouseController = MouseController(
            systemActionsEnabled: options.enableSystemActions,
            startArmed: options.startArmed
        )
        super.init()
    }
    
    static func main() {
        autoreleasepool {
            let options: CommandLineOptions
            do {
                options = try CommandLineOptions.parse()
            } catch {
                fputs("\(error)\n\n\(CommandLineOptions.usage)\n", stderr)
                exit(2)
            }

            if options.showHelp {
                print(CommandLineOptions.usage)
                exit(0)
            }

            let app = NSApplication.shared
            let delegate = AirDeskNativeApp(options: options)
            app.delegate = delegate
            app.run()
        }
    }
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        start()
    }
    
    func start() {
        cameraManager.delegate = self
        visionTracker.delegate = self
        cameraManager.checkPermissionsAndStart()

        if options.enableSystemActions {
            let accessibilityOptions = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
            accessibilityTrusted = AXIsProcessTrustedWithOptions(accessibilityOptions as CFDictionary)
            if !accessibilityTrusted {
                print("Please grant Accessibility permissions in System Settings -> Privacy & Security -> Accessibility.")
            }
            print("System actions enabled. Press S to arm/disarm, M for mode, X/Y to flip axes. Armed: \(mouseController.isArmed)")
        } else {
            print("System actions disabled. Run with --enable-system-actions to allow real mouse control.")
        }

        installKeyMonitor()
        
        // Init the overlay trackpad bounds using the mouse controller configuration
        overlayWindowManager.updateTrackpadBounds(
            x: mouseController.trackpadX,
            y: mouseController.trackpadY,
            width: mouseController.trackpadWidth,
            height: mouseController.trackpadHeight
        )
        
        // Add the camera preview to the overlay
        overlayWindowManager.setupPreview(session: cameraManager.captureSession)
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let localKeyMonitor {
            NSEvent.removeMonitor(localKeyMonitor)
        }
        if let globalKeyMonitor {
            NSEvent.removeMonitor(globalKeyMonitor)
        }
    }

    private func installKeyMonitor() {
        localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            switch event.charactersIgnoringModifiers?.lowercased() {
            case "s":
                self.toggleArmed()
                return nil
            case "m":
                self.mouseController.toggleControlMode()
                print("Control mode: \(self.mouseController.controlMode.rawValue)")
                return nil
            case "x":
                self.mouseController.toggleFlipX()
                print("Flip X: \(self.mouseController.flipX)")
                return nil
            case "y":
                self.mouseController.toggleFlipY()
                print("Flip Y: \(self.mouseController.flipY)")
                return nil
            default:
                return event
            }
        }

        globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return }
            switch event.charactersIgnoringModifiers?.lowercased() {
            case "s":
                self.toggleArmed()
            case "m":
                self.mouseController.toggleControlMode()
                print("Control mode: \(self.mouseController.controlMode.rawValue)")
            case "x":
                self.mouseController.toggleFlipX()
                print("Flip X: \(self.mouseController.flipX)")
            case "y":
                self.mouseController.toggleFlipY()
                print("Flip Y: \(self.mouseController.flipY)")
            default:
                break
            }
        }
    }

    private func toggleArmed() {
        if mouseController.systemActionsEnabled {
            accessibilityTrusted = AXIsProcessTrusted()
        }
        mouseController.toggleArmed()
        print("System actions armed: \(mouseController.isArmed)")
    }
    
    // MARK: - CameraManagerDelegate
    
    nonisolated func cameraManager(_ manager: CameraManager, didCapture buffer: CMSampleBuffer) {
        visionTracker.processFrame(buffer)
    }
    
    // MARK: - VisionTrackerDelegate
    
    nonisolated func visionTracker(_ tracker: VisionTracker, didDetectHand hand: HandLandmarks?) {
        Task { @MainActor in
            let gestureState = self.gestureEngine.update(handState: hand)
            
            if hand != nil {
                print("Hand detected! Cursor at: \(gestureState.cursorPx?.x ?? 0), \(gestureState.cursorPx?.y ?? 0)")
            } else {
                print("No hand detected")
            }
            
            // Feed the gesture state to the mouse controller
            self.mouseController.update(gestureState: gestureState)
            
            // Feed the gesture state to the visual overlay
            self.overlayWindowManager.updateCursor(
                normalizedPoint: gestureState.cursorPx,
                isPinching: gestureState.pinchActive,
                flipX: self.mouseController.flipX,
                flipY: self.mouseController.flipY
            )
            self.overlayWindowManager.updateDebugState(DebugOverlayState(
                handDetected: hand != nil,
                cursor: gestureState.cursorPx,
                pinchRatio: gestureState.pinchRatio,
                pinchActive: gestureState.pinchActive,
                insideTrackpad: self.mouseController.containsTrackpadPoint(gestureState.cursorPx),
                systemActionsEnabled: self.mouseController.systemActionsEnabled,
                systemActionsArmed: self.mouseController.isArmed,
                accessibilityTrusted: !self.mouseController.systemActionsEnabled || self.accessibilityTrusted,
                controlMode: self.mouseController.controlMode,
                flipX: self.mouseController.flipX,
                flipY: self.mouseController.flipY
            ))
        }
    }
}
