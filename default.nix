with (import (import ./pinned-nixpkgs.nix) { });
let
  pyhafas = python310.pkgs.buildPythonPackage rec {
    pname = "pyhafas";
    version = "0.4.0";
    format = "setuptools";

    src = python310.pkgs.fetchPypi {
      inherit pname version;
      hash = "sha256-y0iUiodad50hR2FqdYgCDc0YbRGXpAo7AETU8AqVoCI=";
    };
    propagatedBuildInputs = with python310.pkgs; [ requests pytz ];

    doCheck = false;
  };

in python310Packages.buildPythonPackage {
  src = builtins.path {
    path = ./.;
    name = "travelhook";
  };

  pname = "travelhook";
  version = "0.0.0";

  propagatedBuildInputs =
    (with python310Packages; [ discordpy setuptools haversine ]) ++ [ pyhafas ];
  format = "pyproject";
}
