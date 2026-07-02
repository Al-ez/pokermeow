try:
    from pokermeow_gui.app import main
except ImportError as error:
    if error.name == "PySide6":
        raise SystemExit(
            "PySide6 is required for the GUI. Install it with: "
            "py -m pip install -r requirements-gui.txt"
        ) from error
    raise


if __name__ == "__main__":
    raise SystemExit(main())
