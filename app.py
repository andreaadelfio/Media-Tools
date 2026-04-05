from media_tools.launcher import main
from media_tools.server import create_app


app = create_app()


if __name__ == "__main__":
    main()
