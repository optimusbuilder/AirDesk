import AVFoundation
import CoreMedia
@preconcurrency import ApplicationServices
import AppKit

@main
@MainActor
final class AirDeskNativeApp: NSObject, NSApplicationDelegate, CameraManagerDelegate, VisionTrackerDelegate {
    
    let cameraManager = CameraManager()
    let visionTracker = VisionTracker()
    let gestureEngine = GestureEngine()
    let mouseController = MouseController()
    let overlayWindowManager = OverlayWindowManager()
    
    static func main() {
        autoreleasepool {
            let app = NSApplication.shared
            let delegate = AirDeskNativeApp()
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
        
        // Ensure accessibility is trusted
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
        let isTrusted = AXIsProcessTrustedWithOptions(options as CFDictionary)
        if !isTrusted {
            print("Please grant Accessibility permissions in System Settings -> Privacy & Security -> Accessibility.")
        }
        
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
            self.overlayWindowManager.updateCursor(normalizedPoint: gestureState.cursorPx, isPinching: gestureState.pinchActive)
        }
    }
}
