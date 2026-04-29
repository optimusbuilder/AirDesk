import AppKit
import CoreGraphics
import AVFoundation

@MainActor
final class OverlayView: NSView {
    
    var trackpadRect: CGRect = .zero
    var cursorPoint: CGPoint? = nil
    var isPinching: Bool = false
    
    private var lastPoint: CGPoint? = nil
    private var velocity: CGFloat = 0.0
    
    override func draw(_ dirtyRect: NSRect) {
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
}

@MainActor
final class OverlayWindowManager {
    
    private var window: NSWindow!
    private var overlayView: OverlayView!
    private var previewLayer: AVCaptureVideoPreviewLayer?
    
    init() {
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
    
    func setupPreview(session: AVCaptureSession) {
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
    func updateTrackpadBounds(x: Double, y: Double, width: Double, height: Double) {
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
    
    func updateCursor(normalizedPoint: NormalizedPoint?, isPinching: Bool) {
        if let point = normalizedPoint {
            let screenFrame = window.frame
            // Convert to NSView bottom-left coordinates
            overlayView.cursorPoint = CGPoint(
                x: CGFloat(point.x) * screenFrame.width,
                y: CGFloat(1.0 - point.y) * screenFrame.height
            )
        } else {
            overlayView.cursorPoint = nil
        }
        overlayView.isPinching = isPinching
        overlayView.needsDisplay = true
    }
}
