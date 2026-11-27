"""Sets the password of the site's "admin" account (db.py, "The admin").

  python -m schnaps_web.tools.set_admin [--db-dir DIR] [--stdin]

The first time it makes the account; afterwards it resets the password and
logs the admin's devices out. It asks for the password twice (--stdin reads
it once from standard input instead, for scripts). Only its salted hash is
stored, like every other account's.

The database is the site's own: SCHNAPS_WEB_DB_DIR, else data/db (the
Docker image sets /data/db). It may run while the site is up: SQLite locks
the file for the short write, and the site reads the account from the file
at every login.

On the server:  docker compose exec schnaps python -m schnaps_web.tools.set_admin
"""

import argparse
import getpass
import sys

from schnaps_web import config as config_lib
from schnaps_web import db as db_lib


def main(argv=None) -> int:
  p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  p.add_argument("--db-dir", default=None,
                 help="the database's directory (default: the site's)")
  p.add_argument("--stdin", action="store_true",
                 help="read the password from standard input, once")
  args = p.parse_args(argv)
  directory = args.db_dir or config_lib.from_env().db_dir
  if not directory:
    print("No database directory (SCHNAPS_WEB_DB_DIR is empty).", file=sys.stderr)
    return 2

  if args.stdin:
    password = sys.stdin.readline().rstrip("\r\n")
  else:
    password = getpass.getpass("New admin password: ")
    if getpass.getpass("Again: ") != password:
      print("The two passwords differ; nothing changed.", file=sys.stderr)
      return 1

  db = db_lib.Db(directory)
  try:
    made = db.set_admin_password(password)
  except db_lib.AccountError as e:
    print(f"{e}; nothing changed.", file=sys.stderr)
    return 1
  finally:
    db.close()
  print(("Made the admin account" if made else "Admin password set")
        + f" in {directory}.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
