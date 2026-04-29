import Foundation

struct GestureState {
    var cursorPx: NormalizedPoint?
    var rawCursorPx: NormalizedPoint?
    var pinchRatio: Double
    var pinchActive: Bool
    var pinchStarted: Bool
    var pinchEnded: Bool
    var trackingStable: Bool
}

class GestureEngine {
    
    // Config: using ratio values relative to hand scale
    var pinchOnThreshold: Double = 0.35
    var pinchOffThreshold: Double = 0.45
    var pinchDebounceMs: Double = 40.0
    
    private var cursorFilter = OneEuroFilter(minCutoff: 1.0, beta: 0.007, dCutoff: 1.0)
    
    private var previousPinchActive: Bool = false
    private var pendingPinchState: Bool = false
    private var pinchStateSince: TimeInterval? = nil
    
    func update(handState: HandLandmarks?) -> GestureState {
        guard let hand = handState, let rawCursor = hand.indexTip else {
            cursorFilter.reset()
            previousPinchActive = false
            pendingPinchState = false
            pinchStateSince = nil
            return GestureState(cursorPx: nil, rawCursorPx: nil, pinchRatio: 0.0, pinchActive: false, pinchStarted: false, pinchEnded: false, trackingStable: false)
        }
        
        let cursor = cursorFilter.apply(point: rawCursor)
        let pinchRatio = computePinchRatio(hand: hand)
        let rawPinch = computeRawPinchActive(pinchRatio: pinchRatio)
        let pinchActive = debouncePinch(rawPinch: rawPinch)
        
        let pinchStarted = pinchActive && !previousPinchActive
        let pinchEnded = previousPinchActive && !pinchActive
        
        previousPinchActive = pinchActive
        
        return GestureState(
            cursorPx: cursor,
            rawCursorPx: rawCursor,
            pinchRatio: pinchRatio,
            pinchActive: pinchActive,
            pinchStarted: pinchStarted,
            pinchEnded: pinchEnded,
            trackingStable: true
        )
    }
    
    private func computePinchRatio(hand: HandLandmarks) -> Double {
        guard let thumb = hand.thumbTip, let index = hand.indexTip else { return Double.infinity }
        let dx = thumb.x - index.x
        let dy = thumb.y - index.y
        let distance = hypot(dx, dy)
        // Divide by handScale so the threshold is consistent regardless of distance to camera
        return distance / hand.handScale
    }
    
    private func computeRawPinchActive(pinchRatio: Double) -> Bool {
        if previousPinchActive {
            return pinchRatio <= pinchOffThreshold
        }
        return pinchRatio <= pinchOnThreshold
    }
    
    private func debouncePinch(rawPinch: Bool) -> Bool {
        let now = ProcessInfo.processInfo.systemUptime
        
        if rawPinch == previousPinchActive {
            pendingPinchState = rawPinch
            pinchStateSince = nil
            return previousPinchActive
        }
        
        if pinchStateSince == nil || pendingPinchState != rawPinch {
            pinchStateSince = now
            pendingPinchState = rawPinch
        }
        
        if let since = pinchStateSince {
            let elapsedMs = (now - since) * 1000.0
            if elapsedMs >= pinchDebounceMs {
                pinchStateSince = nil
                return rawPinch
            }
        }
        
        return previousPinchActive
    }
}
