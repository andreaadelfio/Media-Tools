from media_suite.launcher import main
from media_suite.server import create_app


app = create_app()


if __name__ == "__main__":
    main()
