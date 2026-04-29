import AVFoundation
import CoreMedia

/// Delegate protocol to receive video frames.
protocol CameraManagerDelegate: AnyObject {
    func cameraManager(_ manager: CameraManager, didCapture buffer: CMSampleBuffer)
}

/// Manages the `AVCaptureSession` and camera feed.
final class CameraManager: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable {
    
    let captureSession = AVCaptureSession()
    private let videoDataOutput = AVCaptureVideoDataOutput()
    private let captureQueue = DispatchQueue(label: "com.airdesk.captureQueue")
    
    weak var delegate: CameraManagerDelegate?
    
    override init() {
        super.init()
    }
    
    func checkPermissionsAndStart() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            self.setupAndStartSession()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                if granted {
                    self?.setupAndStartSession()
                } else {
                    print("Camera access denied.")
                }
            }
        default:
            print("Camera access denied or restricted.")
        }
    }
    
    private func setupAndStartSession() {
        captureSession.beginConfiguration()
        if captureSession.canSetSessionPreset(.vga640x480) {
            captureSession.sessionPreset = .vga640x480
        } else {
            print("Preset .vga640x480 not supported. Using default.")
        }
        
        // 1. Look for Desk View Camera (iPhone Continuity Camera)
        let discoverySession = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.deskViewCamera],
            mediaType: .video,
            position: .unspecified
        )
        
        var videoDevice = discoverySession.devices.first
        
        // 2. Fallback to built-in webcam if no Desk View is found
        if videoDevice == nil {
            videoDevice = AVCaptureDevice.default(for: .video)
        }
        
        guard let device = videoDevice else {
            print("No video device found.")
            captureSession.commitConfiguration()
            return
        }
        
        print("Using video device: \(device.localizedName)")
        
        do {
            let videoDeviceInput = try AVCaptureDeviceInput(device: device)
            if captureSession.canAddInput(videoDeviceInput) {
                captureSession.addInput(videoDeviceInput)
            } else {
                print("Could not add video device input.")
                captureSession.commitConfiguration()
                return
            }
        } catch {
            print("Error creating video device input: \(error)")
            captureSession.commitConfiguration()
            return
        }
        
        videoDataOutput.alwaysDiscardsLateVideoFrames = true
        videoDataOutput.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)
        ]
        videoDataOutput.setSampleBufferDelegate(self, queue: captureQueue)
        
        if captureSession.canAddOutput(videoDataOutput) {
            captureSession.addOutput(videoDataOutput)
        } else {
            print("Could not add video data output.")
            captureSession.commitConfiguration()
            return
        }
        
        // We let the Vision framework consume the raw (unmirrored) video feed
        // and we will mirror the X coordinates mathematically in VisionTracker.
        // This ensures the ML model receives the anatomically correct image.
        
        captureSession.commitConfiguration()
        
        // Start the session on a background thread
        DispatchQueue.global(qos: .userInitiated).async {
            self.captureSession.startRunning()
        }
    }
    
    func stopSession() {
        if captureSession.isRunning {
            captureSession.stopRunning()
        }
    }
    
    // MARK: - AVCaptureVideoDataOutputSampleBufferDelegate
    
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        delegate?.cameraManager(self, didCapture: sampleBuffer)
    }
}
