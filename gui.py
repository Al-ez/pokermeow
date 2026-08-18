try:
    from pokermeow_gui.app import main
except ImportError as error:
    if error.name == "PySide6":
        raise SystemExit(
            "PySide6 is required for the GUI. Install it with: "
            "python -m pip install -r requirements.txt"
        ) from error
    raise


if __name__ == "__main__":
    raise SystemExit(main())
