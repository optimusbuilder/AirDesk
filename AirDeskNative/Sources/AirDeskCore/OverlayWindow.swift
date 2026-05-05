import AppKit
import CoreGraphics
import AVFoundation

public struct DebugOverlayState: Sendable {
    public var handDetected: Bool
    public var cursor: NormalizedPoint?
    public var pinchRatio: Double
    public var pinchActive: Bool
    public var insideTrackpad: Bool
    public var systemActionsEnabled: Bool
    public var systemActionsArmed: Bool
    public var accessibilityTrusted: Bool
    public var controlMode: ControlMode
    public var flipX: Bool
    public var flipY: Bool

    public init(
        handDetected: Bool = false,
        cursor: NormalizedPoint? = nil,
        pinchRatio: Double = 0,
        pinchActive: Bool = false,
        insideTrackpad: Bool = false,
        systemActionsEnabled: Bool = false,
        systemActionsArmed: Bool = false,
        accessibilityTrusted: Bool = false,
        controlMode: ControlMode = .relative,
        flipX: Bool = false,
        flipY: Bool = true
    ) {
        self.handDetected = handDetected
        self.cursor = cursor
        self.pinchRatio = pinchRatio
        self.pinchActive = pinchActive
        self.insideTrackpad = insideTrackpad
        self.systemActionsEnabled = systemActionsEnabled
        self.systemActionsArmed = systemActionsArmed
        self.accessibilityTrusted = accessibilityTrusted
        self.controlMode = controlMode
        self.flipX = flipX
        self.flipY = flipY
    }
}

@MainActor
public final class OverlayView: NSView {
    
    public var trackpadRect: CGRect = .zero
    public var cursorPoint: CGPoint? = nil
    public var isPinching: Bool = false
    public var debugState = DebugOverlayState()
    
    private var lastPoint: CGPoint? = nil
    private var velocity: CGFloat = 0.0
    
    public override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        
        guard let context = NSGraphicsContext.current?.cgContext else { return }
        
        // Draw trackpad boundaries
        let strokeColor = NSColor.white.withAlphaComponent(0.4).cgColor
        let fillColor = NSColor.white.withAlphaComponent(0.05).cgColor
        
        context.setFillColor(fillColor)
        context.fill(trackpadRect)
        
        context.setStrokeColor(strokeColor)
        context.setLineWidth(2.0)
        context.stroke(trackpadRect)

        drawDebugHUD()
        
        guard let point = cursorPoint else { return }
        
        // Calculate velocity for the bloom pulse effect
        if let last = lastPoint {
            let distance = hypot(point.x - last.x, point.y - last.y)
            // Exponential smoothing for velocity to avoid rapid flickering
            velocity = 0.8 * velocity + 0.2 * distance
        }
        lastPoint = point
        
        // Dynamic bloom sizing based on velocity
        let baseRadius: CGFloat = isPinching ? 16.0 : 24.0
        let bloomRadius = baseRadius + (velocity * 0.5)
        
        // Setup Radial Gradient
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        
        // Color shifts dynamically: green for pinch, blue/purple for moving, soft white when idle
        let coreColor: NSColor
        let outerColor: NSColor
        
        if isPinching {
            coreColor = NSColor.systemGreen.withAlphaComponent(0.6)
            outerColor = NSColor.systemGreen.withAlphaComponent(0.0)
        } else if velocity > 5.0 {
            coreColor = NSColor.systemPurple.withAlphaComponent(0.4)
            outerColor = NSColor.systemIndigo.withAlphaComponent(0.0)
        } else {
            coreColor = NSColor.white.withAlphaComponent(0.3)
            outerColor = NSColor.white.withAlphaComponent(0.0)
        }
        
        let colors = [coreColor.cgColor, outerColor.cgColor] as CFArray
        let locations: [CGFloat] = [0.0, 1.0]
        
        if let gradient = CGGradient(colorsSpace: colorSpace, colors: colors, locations: locations) {
            context.drawRadialGradient(
                gradient,
                startCenter: point,
                startRadius: 0.0,
                endCenter: point,
                endRadius: bloomRadius,
                options: .drawsAfterEndLocation
            )
        }
    }

    private func drawDebugHUD() {
        let cursorText: String
        if let cursor = debugState.cursor {
            cursorText = String(format: "x=%.3f y=%.3f", cursor.x, cursor.y)
        } else {
            cursorText = "none"
        }

        let lines = [
            "Hand: \(debugState.handDetected ? "detected" : "missing")",
            "Cursor: \(cursorText)",
            String(format: "Pinch ratio: %.3f", debugState.pinchRatio),
            "Pinch active: \(debugState.pinchActive ? "yes" : "no")",
            "Inside trackpad: \(debugState.insideTrackpad ? "yes" : "no")",
            "Mode: \(debugState.controlMode.rawValue)",
            "Flip X/Y: \(debugState.flipX ? "on" : "off") / \(debugState.flipY ? "on" : "off")",
            "System actions: \(debugState.systemActionsEnabled ? "enabled" : "disabled")",
            "Armed: \(debugState.systemActionsArmed ? "yes" : "no")",
            "Accessibility: \(debugState.accessibilityTrusted ? "trusted" : "not trusted")",
        ]
        let text = lines.joined(separator: "\n")

        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 3
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedSystemFont(ofSize: 14, weight: .medium),
            .foregroundColor: NSColor.white,
            .paragraphStyle: paragraph,
        ]
        let attributed = NSAttributedString(string: text, attributes: attributes)
        let textSize = attributed.boundingRect(
            with: NSSize(width: 320, height: CGFloat.greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin]
        ).size

        let padding: CGFloat = 12
        let origin = CGPoint(x: 20, y: bounds.height - textSize.height - padding * 2 - 20)
        let backgroundRect = CGRect(
            x: origin.x,
            y: origin.y,
            width: textSize.width + padding * 2,
            height: textSize.height + padding * 2
        )

        NSColor.black.withAlphaComponent(0.68).setFill()
        NSBezierPath(roundedRect: backgroundRect, xRadius: 8, yRadius: 8).fill()

        attributed.draw(in: CGRect(
            x: backgroundRect.minX + padding,
            y: backgroundRect.minY + padding,
            width: textSize.width,
            height: textSize.height
        ))
    }
}

@MainActor
public final class OverlayWindowManager {
    
    private var window: NSWindow!
    private var overlayView: OverlayView!
    private var previewLayer: AVCaptureVideoPreviewLayer?
    
    public init() {
        let screenFrame = NSScreen.main?.frame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        
        window = NSWindow(contentRect: screenFrame, styleMask: .borderless, backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating // Always on top
        window.ignoresMouseEvents = true // Click-through
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        
        overlayView = OverlayView(frame: screenFrame)
        overlayView.wantsLayer = true // Needed to add sublayers like the camera preview
        window.contentView = overlayView
        
        window.makeKeyAndOrderFront(nil)
    }
    
    public func setupPreview(session: AVCaptureSession) {
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        
        // Put the camera preview in the top-right corner
        let previewWidth: CGFloat = 320
        let previewHeight: CGFloat = 240
        let screenFrame = window.frame
        layer.frame = CGRect(
            x: screenFrame.width - previewWidth - 20,
            y: screenFrame.height - previewHeight - 20,
            width: previewWidth,
            height: previewHeight
        )
        
        layer.cornerRadius = 12
        layer.masksToBounds = true
        layer.borderWidth = 2
        layer.borderColor = NSColor.white.withAlphaComponent(0.5).cgColor
        
        overlayView.layer?.addSublayer(layer)
        previewLayer = layer
    }
    
    /// Maps the normalized trackpad config (from MouseController) to physical screen coordinates
    public func updateTrackpadBounds(x: Double, y: Double, width: Double, height: Double) {
        let screenFrame = window.frame
        let rect = CGRect(
            x: CGFloat(x) * screenFrame.width,
            // NSView coordinate system is bottom-left by default, but we mapped y to top-left in VisionTracker.
            // Let's use standard bottom-left math for NSView drawing or flip the view.
            // Usually, NSView is bottom-left, so a top-left Y of 0.5 means a bottom-left Y of (1.0 - 0.5 - height).
            y: CGFloat(1.0 - y - height) * screenFrame.height,
            width: CGFloat(width) * screenFrame.width,
            height: CGFloat(height) * screenFrame.height
        )
        overlayView.trackpadRect = rect
        overlayView.needsDisplay = true
    }
    
    public func updateCursor(
        normalizedPoint: NormalizedPoint?,
        isPinching: Bool,
        flipX: Bool = false,
        flipY: Bool = false
    ) {
        if let point = normalizedPoint {
            let screenFrame = window.frame
            let displayX = flipX ? 1.0 - point.x : point.x
            let displayY = flipY ? 1.0 - point.y : point.y
            // Convert to NSView bottom-left coordinates
            overlayView.cursorPoint = CGPoint(
                x: CGFloat(displayX) * screenFrame.width,
                y: CGFloat(1.0 - displayY) * screenFrame.height
            )
        } else {
            overlayView.cursorPoint = nil
        }
        overlayView.isPinching = isPinching
        overlayView.needsDisplay = true
    }

    public func updateDebugState(_ state: DebugOverlayState) {
        overlayView.debugState = state
        overlayView.needsDisplay = true
    }
}
