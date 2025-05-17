with (import (import ./pinned-nixpkgs.nix) { });

mkShell {
  inputsFrom = [ (import ./default.nix) ];
  shellHook = ''
    export PATH=.:$PATH
  '';
  packages = [ python310Packages.black python310Packages.pylint sqlite ];
}
