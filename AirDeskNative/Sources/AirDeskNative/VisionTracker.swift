import Vision
import CoreMedia

/// A simple structure to hold normalized point coordinates.
/// Origin (0,0) is top-left, matching screen coordinate systems.
struct NormalizedPoint {
    var x: Double
    var y: Double
}

struct HandLandmarks {
    var points: [VNHumanHandPoseObservation.JointName: NormalizedPoint]
    
    var thumbTip: NormalizedPoint? { points[.thumbTip] }
    var indexTip: NormalizedPoint? { points[.indexTip] }
    var middleTip: NormalizedPoint? { points[.middleTip] }
    var wrist: NormalizedPoint? { points[.wrist] }
    var indexMCP: NormalizedPoint? { points[.indexMCP] }
    
    /// Distance between wrist and indexMCP to use as a normalization scale
    var handScale: Double {
        guard let w = wrist, let m = indexMCP else { return 1.0 }
        let dist = hypot(w.x - m.x, w.y - m.y)
        return max(dist, 0.001)
    }
}

protocol VisionTrackerDelegate: AnyObject {
    func visionTracker(_ tracker: VisionTracker, didDetectHand hand: HandLandmarks?)
}

final class VisionTracker: @unchecked Sendable {
    
    weak var delegate: VisionTrackerDelegate?
    private let handPoseRequest = VNDetectHumanHandPoseRequest()
    
    init() {
        handPoseRequest.maximumHandCount = 1
    }
    
    func processFrame(_ sampleBuffer: CMSampleBuffer) {
        let handler = VNImageRequestHandler(cmSampleBuffer: sampleBuffer, orientation: .down, options: [:])
        
        do {
            try handler.perform([handPoseRequest])
            
            guard let observation = handPoseRequest.results?.first as? VNHumanHandPoseObservation else {
                // No hand detected
                DispatchQueue.main.async {
                    self.delegate?.visionTracker(self, didDetectHand: nil)
                }
                return
            }
            
            // Extract recognized points
            let recognizedPoints = try observation.recognizedPoints(.all)
            
            var extractedPoints = [VNHumanHandPoseObservation.JointName: NormalizedPoint]()
            
            for (jointName, point) in recognizedPoints {
                // Confidence threshold to ignore noisy points
                guard point.confidence > 0.5 else { continue }
                
                // Vision framework uses bottom-left origin.
                // Convert to top-left origin by flipping Y.
                // We also flip X to create a mirror effect.
                let normalizedX = 1.0 - Double(point.location.x)
                let normalizedY = 1.0 - Double(point.location.y)
                
                extractedPoints[jointName] = NormalizedPoint(x: normalizedX, y: normalizedY)
            }
            
            let handLandmarks = HandLandmarks(points: extractedPoints)
            
            DispatchQueue.main.async {
                self.delegate?.visionTracker(self, didDetectHand: handLandmarks)
            }
            
        } catch {
            print("Vision request failed: \(error)")
            DispatchQueue.main.async {
                self.delegate?.visionTracker(self, didDetectHand: nil)
            }
        }
    }
}
