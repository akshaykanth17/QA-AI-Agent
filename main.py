"""
main.py
-------
Entry point for the AI-Assisted Software Testing Agent.

Can be run in any of the following ways:
  1. python main.py
  2. streamlit run main.py
  3. Double-clicking run.bat
"""

import sys


def main():
    try:
        import streamlit.runtime
        if not streamlit.runtime.exists():
            from streamlit.web import cli as stcli
            sys.argv = ["streamlit", "run", __file__]
            sys.exit(stcli.main())
    except Exception:
        pass

    import importlib
    import app.ui
    import app.browser.runner
    import app.test_case_generator
    importlib.reload(app.test_case_generator)
    importlib.reload(app.browser.runner)
    importlib.reload(app.ui)
    app.ui.run_app()


if __name__ == "__main__":
    main()

