import sys
import uvicorn
from colorama import init, Fore, Style
from web.server import app

# Initialize colorama for colored terminal output
init()
def main():
    """Main entry point."""
    # Default settings
    host = "0.0.0.0"
    port = 8000
    
    # Check for custom port in command line
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(Fore.RED + f"Invalid port: {sys.argv[1]}" + Style.RESET_ALL)
            sys.exit(1)
    
    print(Fore.GREEN + f"Starting web server..." + Style.RESET_ALL)
    print(Fore.YELLOW + f"Server will be available at: http://localhost:{port}" + Style.RESET_ALL)
    print(Fore.YELLOW + "Press Ctrl+C to stop" + Style.RESET_ALL)
    print()
    
    try:
        # Import and run the FastAPI app
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print()
        print(Fore.YELLOW + "\nServer stopped by user" + Style.RESET_ALL)
        sys.exit(0)
    except Exception as e:
        print()
        print(Fore.RED + f"\nError: {e}" + Style.RESET_ALL)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
