"""scripts/batch/lua_e2e.py helpers: the object list of Lua's src/Makefile and the counter merge.

The end-to-end run itself needs the Lua tarballs and is not part of the unit tests
(docs/lua_case_study.md has the command and the results).

Run from the repo root:  python3 -m unittest tests.test_lua_e2e -v
"""
import json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts', 'batch'))
import lua_e2e as L

MAKEFILE = '''CORE_O=	lapi.o lcode.o
LIB_O=	lauxlib.o linit.o
BASE_O= $(CORE_O) $(LIB_O) $(MYOBJS)

LUA_T=	lua
LUA_O=	lua.o

LUAC_O=	luac.o
'''


class Helpers(unittest.TestCase):
    def test_makefile_objects_are_the_lua_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'Makefile')
            with open(p, 'w') as f:
                f.write(MAKEFILE)
            self.assertEqual(L.makefile_objects(p), ['lapi.c', 'lcode.c', 'lauxlib.c', 'linit.c', 'lua.c'])

    def test_counters_of_all_processes_are_added(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, branches in enumerate([[{'id': 1, 'true': 2, 'false': 0}],
                                          [{'id': 1, 'true': 1, 'false': 3}, {'id': 4, 'true': 0, 'false': 1}]]):
                paths.append(os.path.join(d, f'cov.{i}.json'))
                with open(paths[-1], 'w') as f:
                    json.dump({'branches': branches}, f)
            self.assertEqual(L.merge_counters(paths), {1: {'id': 1, 'true': 3, 'false': 3},
                                                       4: {'id': 4, 'true': 0, 'false': 1}})


if __name__ == '__main__':
    unittest.main()
