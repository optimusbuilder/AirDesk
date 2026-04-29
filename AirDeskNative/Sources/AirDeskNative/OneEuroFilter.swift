import Foundation

/// Simple first-order low-pass filter used internally by the 1€ filter.
struct LowPassFilter {
    private var y: Double = 0.0
    private var alpha: Double
    private var initialized: Bool = false
    
    init(alpha: Double) {
        self.alpha = max(0.0, min(alpha, 1.0))
    }
    
    mutating func apply(value: Double, alpha newAlpha: Double? = nil) -> Double {
        if let newAlpha = newAlpha {
            self.alpha = max(0.0, min(newAlpha, 1.0))
        }
        
        if !initialized {
            self.y = value
            self.initialized = true
        } else {
            self.y = self.alpha * value + (1.0 - self.alpha) * self.y
        }
        
        return self.y
    }
    
    mutating func reset() {
        self.initialized = false
        self.y = 0.0
    }
    
    var lastValue: Double { y }
}

/// Adaptive low-pass filter for 2D cursor positions.
struct OneEuroFilter {
    var minCutoff: Double
    var beta: Double
    var dCutoff: Double
    
    private var xFilter = LowPassFilter(alpha: 1.0)
    private var yFilter = LowPassFilter(alpha: 1.0)
    private var dxFilter = LowPassFilter(alpha: 1.0)
    private var dyFilter = LowPassFilter(alpha: 1.0)
    
    private var lastTime: TimeInterval?
    private var initialized = false
    
    init(minCutoff: Double = 1.0, beta: Double = 0.007, dCutoff: Double = 1.0) {
        self.minCutoff = minCutoff
        self.beta = beta
        self.dCutoff = dCutoff
    }
    
    mutating func apply(point: NormalizedPoint, timestamp: TimeInterval = ProcessInfo.processInfo.systemUptime) -> NormalizedPoint {
        let x = point.x
        let y = point.y
        
        guard initialized, let lastTime = lastTime else {
            _ = xFilter.apply(value: x)
            _ = yFilter.apply(value: y)
            _ = dxFilter.apply(value: 0.0)
            _ = dyFilter.apply(value: 0.0)
            self.lastTime = timestamp
            self.initialized = true
            return point
        }
        
        var dt = timestamp - lastTime
        if dt <= 0.0 {
            dt = 1.0 / 30.0 // Assume ~30 FPS as fallback
        }
        self.lastTime = timestamp
        
        let rate = 1.0 / dt
        
        // Estimate the derivative (speed) for each axis
        let dx = (x - xFilter.lastValue) * rate
        let dy = (y - yFilter.lastValue) * rate
        
        // Low-pass filter the derivative
        let dAlpha = OneEuroFilter.smoothingFactor(rate: rate, cutoff: dCutoff)
        let edx = dxFilter.apply(value: dx, alpha: dAlpha)
        let edy = dyFilter.apply(value: dy, alpha: dAlpha)
        
        // Adapt the cutoff frequency based on the speed
        let speed = hypot(edx, edy)
        let cutoff = minCutoff + beta * speed
        
        // Low-pass filter the signal with the adapted cutoff
        let alpha = OneEuroFilter.smoothingFactor(rate: rate, cutoff: cutoff)
        let fx = xFilter.apply(value: x, alpha: alpha)
        let fy = yFilter.apply(value: y, alpha: alpha)
        
        return NormalizedPoint(x: fx, y: fy)
    }
    
    mutating func reset() {
        xFilter.reset()
        yFilter.reset()
        dxFilter.reset()
        dyFilter.reset()
        lastTime = nil
        initialized = false
    }
    
    private static func smoothingFactor(rate: Double, cutoff: Double) -> Double {
        let tau = 1.0 / (2.0 * .pi * cutoff)
        return 1.0 / (1.0 + tau * rate)
    }
}
