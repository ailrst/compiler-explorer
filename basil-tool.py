#!/usr/bin/python3
import subprocess
import argparse
import tempfile
import hashlib
import os
import sys
import logging

READELF_BIN="/usr/bin/readelf"
BASIL_JAR="/home/am/Documents/programming/2023/bil-to-boogie-translator/target/scala-3.1.0/wptool-boogie-assembly-0.0.1.jar $WORKDIR/out.adt"
DEFAULT_LOGGER_NAME = 'default_logger'


def get_tempdir(seed: str):
    m = hashlib.md5()
    m.update(seed.encode('utf8'))
    dir_name = os.path.join(tempfile.gettempdir(), "basil-tool", m.hexdigest())
    if not os.path.exists(dir_name):
        logging.info("Created Dir %s", dir_name)
        os.makedirs(dir_name)
    else:
        logging.info("Dir Exists %s", dir_name )
    return dir_name

def make_tempdir(ignored: str):
    return tempfile.mkdtemp()

def bin_name(tmp_dir) -> str:
    bin_file = os.path.join(tmp_dir, "a.out")
    return bin_file

def read_write_binary(tmp_dir:str, filename: str) -> str:
    """
    Save binary from stdin.
    """

    bin_hash = hashlib.sha3_256()
    content = sys.stdin.buffer.read()
    bin_hash.update(content)
    bin_file = bin_name(tmp_dir)

    hash_file = os.path.join(tmp_dir, "bin_hash.sha256")
    hex_hash = bin_hash.hexdigest()

    if (os.path.exists(hash_file)):
        logging.info("Binary Exists")
        with open(hash_file, 'r') as f:
            old_hash = f.read()
        if old_hash != hex_hash:
            logging.info("Error: binary mismatch, got the binary from a different compilation?")
    else:
        logging.info("Writing binary")
        with open(hash_file, 'w') as f:
            f.write(hex_hash)
        with open(bin_file, 'wb') as f:
            f.write(content)

    logging.info("Loaded binary: %s", hex_hash)
    return bin_file


def run_bap_lift(tmp_dir: str, use_asli: bool):

    adtfile = f"{tmp_dir}/out.adt"
    birfile = f"{tmp_dir}/out.bir"

    binary = bin_name(tmp_dir)

    command = (f"/usr/bin/podman run -v {tmp_dir}:{tmp_dir} -w {tmp_dir} ghcr.io/uq-pac/basil-dev bap {binary}").split(" ")
    args = [ "-d", f"adt:{adtfile}", "-d", f"bir:{birfile}"]
    #if use_asli:
    #    args += ["--primus-lisp-semantics=disable"]
    #else:
    #    args += ["--primus-lisp-semantics=enable"]

    command += args
    logging.info("command: %s", command)
    if not (os.path.exists(adtfile) and os.path.exists(birfile)):
        subprocess.run(command, check=True)

    return {"adt": adtfile, "bir": birfile, "default": birfile}

def run_readelf(tmp_dir):
    command = [READELF_BIN, "-s", "-r", "-W", bin_name(tmp_dir)]
    res = subprocess.run(command, capture_output=True)
    print(res.stdout)
    print(res.stderr)
    readelf_file = f"{tmp_dir}/out.relf"

    with open(readelf_file, "w") as f:
        f.write(res.stdout.decode('utf-8'))

    return {"relf": readelf_file, "default": readelf_file}

def run_basil(tmp_dir: str):
    boogie_file = f"{tmp_dir}/out.bpl"
    outputs = {"boogie": boogie_file}

    # dependencies
    outputs.update(run_bap_lift(tmp_dir, False))
    outputs.update(run_readelf(tmp_dir))
    outputs["default"] = boogie_file

    adtfile = outputs['adt']
    birfile = outputs['bir']
    readelf_file = outputs['relf']

    command = f"java -jar /home/am/Documents/programming/2023/bil-to-boogie-translator/target/scala-3.1.0/wptool-boogie-assembly-0.0.1.jar".split(" ") + [adtfile, readelf_file, boogie_file]
    res = subprocess.run(command, capture_output=True, check=True)

    return outputs

def run_boogie(tmp_dir: str, source_dir):
    outputs = run_basil(tmp_dir)
    outputs.update(run_bap_lift(tmp_dir, False))
    outputs.update(run_readelf(tmp_dir))

    boogie_file = outputs['boogie']
    adt_file = outputs['adt']
    bir_file = outputs['bir']
    readelf_file = outputs['relf']

    command = ["boogie", boogie_file]
    res = subprocess.run(command, capture_output=True, check=True)

    return outputs


def cleanup_tempdirs():
    """
    Because temporary directories are shared between invocations we need to cleanup those that are no longer needed.

    """
    return 0

def main(tmp_dir):
    parser = argparse.ArgumentParser(
                    prog='BasilTool',
                    description='Runs Basil and Associated Tools',
                    epilog='')
    parser.add_argument('-d', '--directory',  required=True, help="Used to identify the compilation")
    parser.add_argument('-t', '--tool', help="Which tool to run, basil/bap/readelf", default="basil")
    parser.add_argument('-o', '--output', help="Which output to send to stdout", default="default")

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    args = parser.parse_args()
    logging.debug(args)
    #tmp_dir = get_tempdir(args.directory)
    read_write_binary(tmp_dir, "fname")

    outputs = {}
    if args.tool == "readelf":
        outputs = run_readelf(tmp_dir)
    elif args.tool == "bap":
        outputs = run_bap_lift(tmp_dir, False)
    elif args.tool == "basil":
        outputs = run_basil(tmp_dir)
    else:
        print("Allowed tools: [readelf, bap, basil]")
        return 1

    if args.output not in outputs:
        print("Output unavailable, allowed are:", ", ".join(outputs.keys()))
        return 1
    with open(outputs[args.output], 'r') as f:
        print(f.read())
    return 0




if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        main(tmp_dir)
