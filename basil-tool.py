#!/usr/bin/python3
import subprocess
import argparse
import tempfile
import hashlib
import os
import sys
import logging
import shutil

READELF_BIN=shutil.which("readelf")
JAVA_BIN=shutil.which("java")
BOOGIE_BIN=shutil.which("boogie")  # /root/.dotnet/tools/boogie
BAP_BIN=shutil.which("bap")
BASIL_JAR="/target/scala-3.3.1/wptool-boogie-assembly-0.0.1.jar"

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
        logging.info("Writing binary %s", bin_file)
        with open(hash_file, 'w') as f:
            f.write(hex_hash)
        with open(bin_file, 'wb') as f:
            f.write(content)

    logging.info("Loaded binary: %s %s", hex_hash, bin_file)
    print("binary", content)
    return bin_file


def run_bap_lift(tmp_dir: str, use_asli: bool):
    logging.info("Bap")
    adtfile = f"{tmp_dir}/out.adt"
    birfile = f"{tmp_dir}/out.bir"

    binary = bin_name(tmp_dir)

    command = (f"{BAP_BIN} {binary}").split(" ")
    args = [ "-d", f"adt:{adtfile}", "-d", f"bir:{birfile}"]
    #if use_asli:
    #    args += ["--primus-lisp-semantics=disable"]
    #else:
    #    args += ["--primus-lisp-semantics=enable"]

    command += args
    logging.info("command: %s", command)
    if not (os.path.exists(adtfile) and os.path.exists(birfile)):
        res = subprocess.run(command, check=True)
        logging.info(res.stdout)
        logging.info(res.stderr)

    return {"adt": adtfile, "bir": birfile, "default": birfile}

def run_readelf(tmp_dir):
    logging.info("Readelf")
    command = [READELF_BIN, "-s", "-r", "-W", bin_name(tmp_dir)]
    res = subprocess.run(command, capture_output=True, check=True)
    logging.info(res.stdout)
    logging.info(res.stderr)

    readelf_file = f"{tmp_dir}/out.relf"

    with open(readelf_file, "w") as f:
        f.write(res.stdout.decode('utf-8'))

    return {"relf": readelf_file, "default": readelf_file}

def run_basil(tmp_dir: str, spec: str | None =None):
    logging.info("Basil")
    boogie_file = f"{tmp_dir}/boogie_out.bpl"
    outputs = {"boogie": boogie_file, "basil-il": "before-analysis.il.txt"}

    # dependencies
    outputs.update(run_bap_lift(tmp_dir, False))
    outputs.update(run_readelf(tmp_dir))
    outputs["default"] = boogie_file

    adtfile = outputs['adt']
    birfile = outputs['bir']
    readelf_file = outputs['relf']
    os.chdir(tmp_dir) # so  the output file is in the right dir
    command = [JAVA_BIN, "-jar", BASIL_JAR]
    files = ["-a", adtfile, "-r", readelf_file, "-o", boogie_file, '--dump-il']
    if spec:
        files += ["-s", spec]
        outputs["spec"] = spec
    command += files
    logging.info(command)
    res = subprocess.run(command, capture_output=True, check=False)
    logging.info(res.stdout.decode('utf-8'))
    logging.info(res.stderr.decode('utf-8'))

    return outputs


def run_boogie_only(tmp_dir: str, args: list = [], spec = None):
    binary = bin_name(tmp_dir)

    boogie_in = f"{tmp_dir}/boogie-in-source.bpl"

    with open(binary, 'r') as f: # because boogie checks the file extension
        with open(boogie_in, 'w') as o:
            t = f.read()
            o.write(t)

    command = [BOOGIE_BIN, boogie_in]
    command += args
    logging.info("command: %s", command)


    res = subprocess.run(command, capture_output=True)
    logging.info(res.stdout)
    logging.info(res.stderr)

    boogie_file = f"{tmp_dir}/out.boogie"

    with open(boogie_file, "w") as f:
        f.write(res.stderr.decode('utf-8'))
        f.write(res.stdout.decode('utf-8'))

    return {"boogie": boogie_file, "default": boogie_file}


def run_boogie(tmp_dir: str, args: list = [], spec = None):
    outputs = run_basil(tmp_dir, spec)

    boogie_file = outputs['boogie']
    adt_file = outputs['adt']
    bir_file = outputs['bir']
    readelf_file = outputs['relf']

    command = [BOOGIE_BIN, boogie_file]
    command += args
    res = subprocess.run(command, capture_output=True, check=True)
    out = res.stdout.decode('utf-8')
    err = res.stderr.decode('utf-8')


    boogie_outbothfile = f"{tmp_dir}/boogie_stdout_stderr"
    boogie_out = f"{tmp_dir}/boogie_stdout"
    boogie_err = f"{tmp_dir}/boogie_stderr"

    with open(boogie_out, 'w') as f:
        f.write(out)

    with open(boogie_err, 'w') as f:
        f.write(err)

    with open(boogie_outbothfile, 'w') as f:
        f.write(out)
        f.write(err)

    outputs.update({
        "boogie_stdout": boogie_out,
        "boogie_stderr": boogie_err,
        "boogie_stdout_stderr": boogie_outbothfile
        })

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
    parser.add_argument('sourcefile')
    parser.add_argument('-d', '--directory',  required=False, help="Used to identify the compilation")
    parser.add_argument('-t', '--tool', help="Which tool to run, basil/bap/readelf", default="basil")
    parser.add_argument('-o', '--output', help="Which output to send to stdout", default="default")
    parser.add_argument('-a', '--args', help="Extra args to pass to the tool", default=[])
    parser.add_argument('-s', '--spec', help="Specfile for basil")
    parser.add_argument('-v', '--verbose', help="Enable log output", action="store_true")


    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.ERROR)


    logging.info(args)


    data = None
    with open(args.sourcefile, 'rb') as f:
        data = f.read()
    with open(bin_name(tmp_dir), 'wb') as f:
        f.write(data)


    # Copy spec
    spec = None
    if (args.spec):
        spec = f"{tmp_dir}/in.spec"
        specfile = None
        with open(os.path.join(args.directory, args.spec), 'r') as f:
            specfile = f.read()
            #print(specfile)
        with open(spec, 'w') as f:
            f.write(specfile)


# TODO: give basil spec files
# TODO: run boogie
# TODO: primus lifter and asli lifter

    outputs = {}

    if (args.args):
        args.args = args.args.split(" ")

    if args.tool == "readelf":
        outputs = run_readelf(tmp_dir)
    elif args.tool == "bap":
        outputs = run_bap_lift(tmp_dir, False)
    elif args.tool == "basil":
        outputs = run_basil(tmp_dir, spec)
    elif args.tool == "boogie":
        outputs = run_boogie(tmp_dir, args.args, spec)
    elif args.tool == "boogie-source":
        outputs = run_boogie_only(tmp_dir, args.args, spec)
    else:
        print("Allowed tools: [readelf, bap, basil, boogie, boogie-source]")
        exit(1)

    if args.output not in outputs:
        print("Output unavailable, allowed are:", ", ".join(outputs.keys()))
        exit(1)

    with open(outputs[args.output], 'r') as f:
        logging.info("Printinng output: %s", outputs[args.output])
        print(f.read())

    if args.directory:
        with open(os.path.join(args.directory, "stdout"), "w") as foutfile:
            with open(outputs[args.output], 'r') as fwrite:
                foutfile.write(fwrite.read())

    exit(0)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        main(tmp_dir)
