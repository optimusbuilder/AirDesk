import CoreGraphics
import AppKit

public enum MouseEventAction: Equatable {
    case move
    case down
    case drag
    case up
}

public enum ControlMode: String, Sendable {
    case relative
    case absolute
}

public protocol MouseEventPosting {
    func post(action: MouseEventAction, at point: CGPoint)
    func currentLocation() -> CGPoint
}

public struct CGEventMouseEventPoster: MouseEventPosting {
    public init() {}

    public func post(action: MouseEventAction, at point: CGPoint) {
        let mouseType: CGEventType
        switch action {
        case .move:
            mouseType = .mouseMoved
        case .down:
            mouseType = .leftMouseDown
        case .drag:
            mouseType = .leftMouseDragged
        case .up:
            mouseType = .leftMouseUp
        }

        if let event = CGEvent(mouseEventSource: nil, mouseType: mouseType, mouseCursorPosition: point, mouseButton: .left) {
            event.post(tap: .cghidEventTap)
        }
    }

    public func currentLocation() -> CGPoint {
        CGEvent(source: nil)?.location ?? .zero
    }
}

public class MouseController {
    
    // Virtual trackpad boundaries (normalized screen space or physical screen space)
    // For "hands on surface", we define a specific bounding box where the hand should be.
    // Normalized coordinates (0 to 1) relative to camera frame.
    // Example: bottom center of camera frame
    public var trackpadX: Double = 0.10
    public var trackpadY: Double = 0.10
    public var trackpadWidth: Double = 0.80
    public var trackpadHeight: Double = 0.80
    public var controlMode: ControlMode = .relative
    public var flipX: Bool = false
    public var flipY: Bool = true
    public var pointerSensitivity: Double = 1.35
    public var movementDeadzone: Double = 0.0025
    
    // Active dragging state
    private var isDragging: Bool = false
    private var lastTrackpadPoint: NormalizedPoint?

    private let screenBounds: CGRect
    private let eventPoster: MouseEventPosting

    public var systemActionsEnabled: Bool
    public var isArmed: Bool

    public init(
        systemActionsEnabled: Bool = false,
        startArmed: Bool = false,
        screenBounds: CGRect = CGDisplayBounds(CGMainDisplayID()),
        eventPoster: MouseEventPosting = CGEventMouseEventPoster()
    ) {
        self.systemActionsEnabled = systemActionsEnabled
        self.isArmed = systemActionsEnabled && startArmed
        self.screenBounds = screenBounds
        self.eventPoster = eventPoster
    }

    public func setArmed(_ armed: Bool) {
        isArmed = systemActionsEnabled && armed
        if !isArmed, isDragging {
            releaseDrag()
        }
        if !isArmed {
            lastTrackpadPoint = nil
        }
    }

    public func toggleArmed() {
        setArmed(!isArmed)
    }

    public func containsTrackpadPoint(_ point: NormalizedPoint?) -> Bool {
        guard let point else { return false }
        return point.x >= trackpadX && point.x <= (trackpadX + trackpadWidth) &&
            point.y >= trackpadY && point.y <= (trackpadY + trackpadHeight)
    }

    public func toggleControlMode() {
        controlMode = controlMode == .relative ? .absolute : .relative
        lastTrackpadPoint = nil
    }

    public func toggleFlipX() {
        flipX.toggle()
        lastTrackpadPoint = nil
    }

    public func toggleFlipY() {
        flipY.toggle()
        lastTrackpadPoint = nil
    }
    
    public func update(gestureState: GestureState) {
        guard systemActionsEnabled, isArmed else {
            if isDragging {
                releaseDrag()
            }
            lastTrackpadPoint = nil
            return
        }

        guard let cursor = gestureState.cursorPx else {
            // Hand lost, release any active drags
            if isDragging {
                releaseDrag()
            }
            lastTrackpadPoint = nil
            return
        }
        
        // 1. Map camera cursor to trackpad zone
        // Only move the mouse if the finger is inside the trackpad zone
        guard containsTrackpadPoint(cursor) else {
            if isDragging {
                releaseDrag()
            }
            lastTrackpadPoint = nil
            return
        }
        
        let trackpadPoint = localTrackpadPoint(from: cursor)
        let screenPoint: CGPoint
        switch controlMode {
        case .relative:
            if let relativePoint = relativeScreenPoint(from: trackpadPoint) {
                screenPoint = relativePoint
            } else if gestureState.pinchStarted {
                screenPoint = clampToScreen(eventPoster.currentLocation())
            } else {
                return
            }
        case .absolute:
            screenPoint = absoluteScreenPoint(from: trackpadPoint)
        }
        
        if gestureState.pinchStarted {
            startDrag(at: screenPoint)
        } else if gestureState.pinchEnded {
            releaseDrag(at: screenPoint)
        } else if isDragging {
            moveDrag(to: screenPoint)
        } else {
            moveCursor(to: screenPoint)
        }
    }

    private func localTrackpadPoint(from cursor: NormalizedPoint) -> NormalizedPoint {
        NormalizedPoint(
            x: (cursor.x - trackpadX) / trackpadWidth,
            y: (cursor.y - trackpadY) / trackpadHeight
        )
    }

    private func orientedPoint(_ point: NormalizedPoint) -> NormalizedPoint {
        NormalizedPoint(
            x: flipX ? 1.0 - point.x : point.x,
            y: flipY ? 1.0 - point.y : point.y
        )
    }

    private func absoluteScreenPoint(from point: NormalizedPoint) -> CGPoint {
        lastTrackpadPoint = point
        let oriented = orientedPoint(point)
        return clampToScreen(CGPoint(
            x: screenBounds.minX + CGFloat(oriented.x) * screenBounds.width,
            y: screenBounds.minY + CGFloat(oriented.y) * screenBounds.height
        ))
    }

    private func relativeScreenPoint(from point: NormalizedPoint) -> CGPoint? {
        defer { lastTrackpadPoint = point }
        guard let lastTrackpadPoint else {
            return nil
        }

        var dx = point.x - lastTrackpadPoint.x
        var dy = point.y - lastTrackpadPoint.y
        if flipX { dx = -dx }
        if flipY { dy = -dy }

        if hypot(dx, dy) < movementDeadzone {
            return nil
        }

        let current = eventPoster.currentLocation()
        return clampToScreen(CGPoint(
            x: current.x + CGFloat(dx * pointerSensitivity) * screenBounds.width,
            y: current.y + CGFloat(dy * pointerSensitivity) * screenBounds.height
        ))
    }

    private func clampToScreen(_ point: CGPoint) -> CGPoint {
        CGPoint(
            x: min(max(point.x, screenBounds.minX), screenBounds.maxX),
            y: min(max(point.y, screenBounds.minY), screenBounds.maxY)
        )
    }
    
    // MARK: - CGEvent Helpers
    
    private func moveCursor(to point: CGPoint) {
        eventPoster.post(action: .move, at: point)
    }
    
    private func startDrag(at point: CGPoint) {
        isDragging = true
        eventPoster.post(action: .down, at: point)
    }
    
    private func moveDrag(to point: CGPoint) {
        eventPoster.post(action: .drag, at: point)
    }
    
    private func releaseDrag(at point: CGPoint? = nil) {
        isDragging = false
        // If we don't have a point (e.g. hand lost), query the current mouse location
        let targetPoint = point ?? eventPoster.currentLocation()
        eventPoster.post(action: .up, at: targetPoint)
    }
}
