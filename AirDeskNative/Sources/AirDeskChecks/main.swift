import AirDeskCore
import CoreGraphics
import Foundation
import Vision

typealias ADPoint = AirDeskCore.NormalizedPoint

@main
struct AirDeskChecks {
    static func main() throws {
        try checkCommandLineOptions()
        checkGestureEngine()
        checkMouseControllerSafety()
        print("AirDeskChecks passed")
    }

    private static func checkCommandLineOptions() throws {
        let defaults = try CommandLineOptions.parse(["AirDeskNative"])
        expect(defaults.enableSystemActions == false, "system actions should default to disabled")
        expect(defaults.startArmed == false, "start armed should default to false")

        do {
            _ = try CommandLineOptions.parse(["AirDeskNative", "--start-armed"])
            throw CheckFailure("--start-armed without --enable-system-actions should fail")
        } catch CommandLineOptionsError.startArmedRequiresSystemActions {
            // Expected.
        }

        let armed = try CommandLineOptions.parse([
            "AirDeskNative",
            "--enable-system-actions",
            "--start-armed",
        ])
        expect(armed.enableSystemActions, "system actions should parse as enabled")
        expect(armed.startArmed, "start armed should parse as enabled")
    }

    private static func checkGestureEngine() {
        let clock = TestClock()
        let engine = GestureEngine(timeProvider: clock.now)

        clock.advance(by: 0.033)
        let cursor = engine.update(handState: makeHand(index: ADPoint(x: 0.4, y: 0.5)))
        expect(cursor.cursorPx == ADPoint(x: 0.4, y: 0.5), "first cursor should pass through")
        expect(cursor.trackingStable, "tracked hand should be stable")

        clock.advance(by: 0.033)
        let lost = engine.update(handState: nil)
        expect(lost.cursorPx == nil, "tracking loss should clear cursor")
        expect(lost.pinchActive == false, "tracking loss should clear pinch")

        let pinchClock = TestClock()
        let pinchEngine = GestureEngine(timeProvider: pinchClock.now)
        pinchEngine.pinchOnThreshold = 0.35
        pinchEngine.pinchOffThreshold = 0.45
        pinchEngine.pinchDebounceMs = 40

        pinchClock.advance(by: 0.033)
        _ = pinchEngine.update(handState: pinchedHand())
        pinchClock.advance(by: 0.020)
        let stillOff = pinchEngine.update(handState: pinchedHand())
        pinchClock.advance(by: 0.030)
        let nowOn = pinchEngine.update(handState: pinchedHand())

        expect(stillOff.pinchActive == false, "pinch should wait for debounce")
        expect(nowOn.pinchActive, "pinch should activate after debounce")
        expect(nowOn.pinchStarted, "pinch should emit a start edge")
    }

    private static func checkMouseControllerSafety() {
        let disabledPoster = RecordingMouseEventPoster()
        let disabled = MouseController(
            systemActionsEnabled: false,
            startArmed: false,
            screenBounds: CGRect(x: 0, y: 0, width: 1000, height: 500),
            eventPoster: disabledPoster
        )
        disabled.update(gestureState: GestureState(
            cursorPx: ADPoint(x: 0.5, y: 0.5),
            trackingStable: true
        ))
        expect(disabledPoster.events.isEmpty, "disabled controller should post no events")

        let armedPoster = RecordingMouseEventPoster()
        let armed = MouseController(
            systemActionsEnabled: true,
            startArmed: true,
            screenBounds: CGRect(x: 0, y: 0, width: 1000, height: 500),
            eventPoster: armedPoster
        )
        armed.update(gestureState: GestureState(
            cursorPx: ADPoint(x: 0.5, y: 0.5),
            trackingStable: true
        ))
        expect(armedPoster.events.isEmpty, "relative mode should anchor before moving")

        armed.update(gestureState: GestureState(
            cursorPx: ADPoint(x: 0.58, y: 0.5),
            trackingStable: true
        ))
        expect(armedPoster.events.count == 1, "relative mode should post one move after a delta")
        expect(armedPoster.events[0].action == .move, "relative controller should move cursor")
        expect(pointsAreClose(armedPoster.events[0].point, CGPoint(x: 135, y: 0)), "relative movement should use desk delta")

        armed.update(gestureState: GestureState(
            cursorPx: ADPoint(x: 0.5, y: 0.5),
            pinchActive: true,
            pinchStarted: true,
            trackingStable: true
        ))
        armed.setArmed(false)
        expect(armedPoster.events.last == RecordedMouseEvent(action: .up, point: .zero), "disarming should release drag")
    }

    private static func makeHand(
        thumb: ADPoint = ADPoint(x: 0.7, y: 0.5),
        index: ADPoint = ADPoint(x: 0.4, y: 0.5),
        wrist: ADPoint = ADPoint(x: 0.1, y: 0.5),
        indexMCP: ADPoint = ADPoint(x: 0.3, y: 0.5)
    ) -> HandLandmarks {
        HandLandmarks(points: [
            .thumbTip: thumb,
            .indexTip: index,
            .wrist: wrist,
            .indexMCP: indexMCP,
        ])
    }

    private static func pinchedHand() -> HandLandmarks {
        makeHand(
            thumb: ADPoint(x: 0.225, y: 0.5),
            index: ADPoint(x: 0.25, y: 0.5),
            wrist: ADPoint(x: 0.1, y: 0.5),
            indexMCP: ADPoint(x: 0.2, y: 0.5)
        )
    }

    private static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        if !condition() {
            fatalError(message)
        }
    }

    private static func pointsAreClose(_ lhs: CGPoint, _ rhs: CGPoint, tolerance: CGFloat = 0.001) -> Bool {
        abs(lhs.x - rhs.x) <= tolerance && abs(lhs.y - rhs.y) <= tolerance
    }
}

private struct CheckFailure: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

private final class TestClock {
    private var time: TimeInterval = 0

    func now() -> TimeInterval {
        time
    }

    func advance(by seconds: TimeInterval) {
        time += seconds
    }
}

private struct RecordedMouseEvent: Equatable {
    let action: MouseEventAction
    let point: CGPoint
}

private final class RecordingMouseEventPoster: MouseEventPosting {
    var events: [RecordedMouseEvent] = []

    func post(action: MouseEventAction, at point: CGPoint) {
        events.append(RecordedMouseEvent(action: action, point: point))
        current = point
    }

    func currentLocation() -> CGPoint {
        current
    }

    private var current = CGPoint.zero
}
