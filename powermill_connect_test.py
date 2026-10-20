import win32com.client


PROG_IDS = [
    "PowerMill.Application",
    "PowerMill.Application.2024",
    "Autodesk.PowerMill.Application",
    "Autodesk.PowerMill.Application.2024",
    "PowerMill.Application.2023",
    "PowerMill.Application.2022",
]


def connect_to_powermill():
    for prog_id in PROG_IDS:
        try:
            app = win32com.client.GetActiveObject(prog_id)
            print(f"CONNECTED via {prog_id}")
            print(type(app))
            print(app)
            return app
        except Exception as exc:
            print(f"FAIL {prog_id}: {type(exc).__name__}: {exc}")

    for prog_id in PROG_IDS:
        try:
            app = win32com.client.Dispatch(prog_id)
            print(f"DISPATCH via {prog_id}")
            print(type(app))
            print(app)
            return app
        except Exception as exc:
            print(f"DISPATCH_FAIL {prog_id}: {type(exc).__name__}: {exc}")

    raise RuntimeError("PowerMill COM object not found. Ensure PowerMill is running and Automation is available.")


if __name__ == "__main__":
    app = connect_to_powermill()
    print("App reference is valid:", bool(app))
    try:
        print("Name:", app.Name)
    except Exception as exc:
        print("Name unavailable:", exc)
