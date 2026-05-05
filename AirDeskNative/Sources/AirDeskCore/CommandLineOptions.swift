import Foundation

public struct CommandLineOptions: Equatable {
    public var enableSystemActions: Bool = false
    public var startArmed: Bool = false
    public var showHelp: Bool = false

    public init(enableSystemActions: Bool = false, startArmed: Bool = false, showHelp: Bool = false) {
        self.enableSystemActions = enableSystemActions
        self.startArmed = startArmed
        self.showHelp = showHelp
    }

    public static func parse(_ arguments: [String] = CommandLine.arguments) throws -> CommandLineOptions {
        var options = CommandLineOptions()
        let suppliedArguments = arguments.dropFirst()

        for argument in suppliedArguments {
            switch argument {
            case "--enable-system-actions":
                options.enableSystemActions = true
            case "--start-armed":
                options.startArmed = true
            case "-h", "--help":
                options.showHelp = true
            default:
                throw CommandLineOptionsError.unknownArgument(argument)
            }
        }

        if options.startArmed && !options.enableSystemActions {
            throw CommandLineOptionsError.startArmedRequiresSystemActions
        }

        return options
    }

    public static let usage = """
    Usage: AirDeskNative [--enable-system-actions] [--start-armed]

    Options:
      --enable-system-actions   Allow AirDesk to post real macOS mouse events.
      --start-armed             Start posting mouse events immediately. Requires --enable-system-actions.
      -h, --help                Show this help text.
    """
}

public enum CommandLineOptionsError: Error, CustomStringConvertible, Equatable {
    case unknownArgument(String)
    case startArmedRequiresSystemActions

    public var description: String {
        switch self {
        case .unknownArgument(let argument):
            return "Unknown argument: \(argument)"
        case .startArmedRequiresSystemActions:
            return "--start-armed requires --enable-system-actions."
        }
    }
}
