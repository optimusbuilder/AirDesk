import CoreGraphics
import AppKit

class MouseController {
    
    // Virtual trackpad boundaries (normalized screen space or physical screen space)
    // For "hands on surface", we define a specific bounding box where the hand should be.
    // Normalized coordinates (0 to 1) relative to camera frame.
    // Example: bottom center of camera frame
    var trackpadX: Double = 0.35
    var trackpadY: Double = 0.35
    var trackpadWidth: Double = 0.30
    var trackpadHeight: Double = 0.30
    
    // Active dragging state
    private var isDragging: Bool = false
    
    private let screenBounds = CGDisplayBounds(CGMainDisplayID())
    
    func update(gestureState: GestureState) {
        guard let cursor = gestureState.cursorPx else {
            // Hand lost, release any active drags
            if isDragging {
                releaseDrag()
            }
            return
        }
        
        // 1. Map camera cursor to trackpad zone
        // Only move the mouse if the finger is inside the trackpad zone
        guard cursor.x >= trackpadX && cursor.x <= (trackpadX + trackpadWidth) &&
              cursor.y >= trackpadY && cursor.y <= (trackpadY + trackpadHeight) else {
            if isDragging {
                releaseDrag()
            }
            return
        }
        
        // 2. Normalize to 0...1 within trackpad bounds
        let nx = (cursor.x - trackpadX) / trackpadWidth
        let ny = (cursor.y - trackpadY) / trackpadHeight
        
        // 3. Map to physical screen pixels
        let screenX = screenBounds.minX + CGFloat(nx) * screenBounds.width
        let screenY = screenBounds.minY + CGFloat(ny) * screenBounds.height
        let screenPoint = CGPoint(x: screenX, y: screenY)
        
        // 4. Handle Clicks / Drags based on Pinch State
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
    
    // MARK: - CGEvent Helpers
    
    private func moveCursor(to point: CGPoint) {
        if let event = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left) {
            event.post(tap: .cghidEventTap)
        }
    }
    
    private func startDrag(at point: CGPoint) {
        isDragging = true
        if let event = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left) {
            event.post(tap: .cghidEventTap)
        }
    }
    
    private func moveDrag(to point: CGPoint) {
        if let event = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDragged, mouseCursorPosition: point, mouseButton: .left) {
            event.post(tap: .cghidEventTap)
        }
    }
    
    private func releaseDrag(at point: CGPoint? = nil) {
        isDragging = false
        // If we don't have a point (e.g. hand lost), query the current mouse location
        let targetPoint = point ?? CGEvent(source: nil)?.location ?? .zero
        if let event = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: targetPoint, mouseButton: .left) {
            event.post(tap: .cghidEventTap)
        }
    }
}
