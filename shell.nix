with (import (import ./pinned-nixpkgs.nix) { });

mkShell {
  inputsFrom = [ (import ./default.nix) ];
  packages = [ python310Packages.black python310Packages.pylint ];
}
