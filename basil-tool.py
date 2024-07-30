#!/usr/bin/python3
import subprocess
import argparse
import tempfile
import hashlib
import os
import sys
import logging
import shutil
import sqlite3
import time

READELF_BIN=shutil.which("readelf")
JAVA_BIN=shutil.which("java")
BOOGIE_BIN=shutil.which("boogie")  # /root/.dotnet/tools/boogie
BAP_BIN=shutil.which("bap")
BASIL_BIN=shutil.which("basil")
# Broken
MODEL_TOOL_BIN="/home/am/Documents/programming/2023/basil-tools/modelTool/bin/Debug/net6.0/linux-x64/modelTool"

DEFAULT_LOGGER_NAME = 'default_logger'

JOB_TABLE = "create table if not exists jobs (job string, resultname string, resultfile string);"

QUEUE_TABLE = "create table if not exists jclaimed (job string unique);"


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

    job = f"baplift_asli:{use_asli}"
    cached = get_cache(tmp_dir, job)
    if ("adt" in cached and "bir" in cached):
        logging.info(f"using cached: {cached}")
        return cached

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

    result = {"adt": adtfile, "bir": birfile, "default": birfile}
    update_cache(tmp_dir, job, result)
    return result

def run_readelf(tmp_dir):
    job = "readelf"
    cached = get_cache(tmp_dir, job)
    if ("relf" in cached) :
        return cached

    logging.info("Readelf")
    command = [READELF_BIN, "-s", "-r", "-W", bin_name(tmp_dir)]
    res = subprocess.run(command, capture_output=True, check=True)
    logging.info(res.stdout)
    logging.info(res.stderr)

    readelf_file = f"{tmp_dir}/out.relf"

    with open(readelf_file, "w") as f:
        f.write(res.stdout.decode('utf-8'))

    result = {"relf": readelf_file, "default": readelf_file}
    update_cache(tmp_dir, job, result)
    return result

def run_basil(tmp_dir: str, args: list = [], spec: str | None = None):
    job = f"basil {args} {spec}"
    cached = get_cache(tmp_dir, job)
    if (len(cached) > 0) :
        logging.info(f"using cached: {cached}")
        return cached
    logging.info("Basil")
    boogie_file = f"{tmp_dir}/boogie_out.bpl"
    outputs = {"boogie": boogie_file, "basil-il": boogie_file + ".il"}

    # dependencies
    outputs.update(run_bap_lift(tmp_dir, False))
    outputs.update(run_readelf(tmp_dir))
    outputs["default"] = boogie_file
    logging.info(f"run-basil  outputs {outputs}")

    adtfile = outputs['adt']
    birfile = outputs['bir']
    readelf_file = outputs['relf']
    #os.chdir(tmp_dir) # so  the output file is in the right dir
    command = [BASIL_BIN]
    files = ["-i", adtfile, "-r", readelf_file, "-o", boogie_file, '--dump-il', outputs['basil-il']]

    if spec:
        files += ["-s", spec]
        outputs["spec"] = spec
    command += files
    logging.info(f"basil command {command}")
    res = subprocess.run(command, capture_output=True, check=False)
    logging.info(res.stdout.decode('utf-8'))
    logging.info(res.stderr.decode('utf-8'))

    logging.info("finish basil")
    update_cache(tmp_dir, job, outputs)
    return outputs


def run_boogie_only(tmp_dir: str, args: list = [], spec = None):
    binary = bin_name(tmp_dir)

    boogie_in = f"{tmp_dir}/boogie-in-source.bpl"

    with open(binary, 'r') as f: # because boogie checks the file extension
        with open(boogie_in, 'w') as o:
            t = f.read()
            o.write(t)

    modelfile = "counterexample.model"
    command = [BOOGIE_BIN, boogie_in]
    command += args + ['/mv', modelfile]
    logging.info("command: %s", command)


    res = subprocess.run(command, capture_output=True)
    logging.info(res.stdout.decode('utf-8'))
    logging.info(res.stderr.decode('utf-8'))
    boogie_file = f"{tmp_dir}/out.boogie"

    output = {"boogie": boogie_file, "default": boogie_file}
    if "error" in res.stdout.decode('utf-8'):
        output.update({"counterexample_model": modelfile})

    with open(boogie_file, "w") as f:
        f.write(res.stderr.decode('utf-8'))
        f.write(res.stdout.decode('utf-8'))

    return output


def run_boogie(tmp_dir: str, args: list = [], spec = None):
    outputs = run_basil(tmp_dir, args, spec)

    boogie_file = outputs['boogie']
    adt_file = outputs['adt']
    bir_file = outputs['bir']
    readelf_file = outputs['relf']
    model_file = "counterexample.model"

    command = [BOOGIE_BIN, boogie_file]
    command += args + ['/mv', model_file]
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
        "boogie_stdout_stderr": boogie_outbothfile,
        })

    if "error" in out:
        outputs.update({"counterexample_model": model_file})


    return outputs

def pretty_print_counterexample(tmp_dir: str, args: list = [], spec = None):
    outputs = run_boogie(tmp_dir, args, spec)

    result = ""

    with open(outputs['boogie_stdout_stderr'], 'r') as i:
        result += i.read()
        result += "\n"

    if ('counterexample_model' in outputs):
        command = [MODEL_TOOL_BIN, outputs['counterexample_model']]
        res = subprocess.run(command, capture_output=True, check=False)
        logging.info(res.stdout.decode('utf-8'))
        logging.info(res.stderr.decode('utf-8'))
        result += res.stdout.decode('utf-8')
        result += res.stderr.decode('utf-8')

    ce_file = "modelTool_stdout"
    outputs.update({'counterexample': ce_file, "default": ce_file})


    with open(ce_file, "w") as f:
        f.write(result)

    return outputs


def cleanup_tempdirs():
    """
    Because temporary directories are shared between invocations we need to cleanup those that are no longer needed.
    """
    return 0

"""
We assume the script is called from godbolt, so if the input files change we
get a different input directory, hance a separate cache database.
We don't checksum any input files etc for this reason.
"""

def has_cache(tmp_dir, job: str):
    con = sqlite3.connect(f"{tmp_dir}/cache.db")
    cur = con.cursor()
    res = cur.execute(f"SELECT EXISTS(SELECT resultfile FROM jobs WHERE job=?);", [job])
    r = res.fetchone()[0]
    logging.info(f"has cache {job} : {r}")
    con.close()
    return r


def get_cache(tmp_dir, job: str):
    con = sqlite3.connect(f"{tmp_dir}/cache.db")
    cur = con.cursor()

    # get cached result
    res = cur.execute(f"SELECT resultname, resultfile FROM jobs WHERE job=?", [job])
    r = res.fetchall()
    r = {oname:ofile for (oname,ofile) in r}
    logging.info(f"cached {job} : {r}")
    return r

    #def claim_job(tmp_dir, job: str):
    #    try:
    #        con = sqlite3.connect(f"{tmp_dir}/cache.db")
    #        cur = con.cursor()
    #        res = cur.execute(f"INSERT INTO jclaimed values (?);", [job])
    #        con.commit()
    #        con.close()
    #        return True
    #    except:
    #        return False
    #
    #
    #
    #def unclaim_job(tmp_dir, job: str):
    #    con = sqlite3.connect(f"{tmp_dir}/cache.db")
    #    cur = con.cursor()
    #    res = cur.execute(f"DELETE FROM jclaimed WHERE job=(?);", [job])
    #    con.commit()
    #    con.close()
    #
def update_cache(tmp_dir, job: str, res):
    data = [(job, oname, ofile) for (oname, ofile) in res.items()]
    logging.info(f"Update cache {job} : {res}")
    con = sqlite3.connect(f"{tmp_dir}/cache.db")
    cur = con.cursor()
    res = cur.executemany(f"INSERT INTO jobs values(?, ?, ?);", data)
    con.commit()
    con.close()

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


    #tmp_dir = get_tempdir(args.directory)

    logging.info(args)


    con = sqlite3.connect(f"{tmp_dir}/cache.db")
    con.execute(JOB_TABLE)
    con.execute(QUEUE_TABLE)


    data = None
    with open(args.sourcefile, 'rb') as f:
        data = f.read()
    with open(bin_name(tmp_dir), 'wb') as f:
        f.write(data)


    def copydirs(d = args.directory):
        job = f"import {d}"
        #claim_job(tmp_dir, job)
        if has_cache(tmp_dir, job):
            return
        for p in os.listdir(d):
            if os.path.isdir(p):
                copydirs(os.path.join(d, p))
            elif os.path.isfile(p):
                with open(os.path.join(d,p), 'rb') as inf:
                    ofname = os.path.join(tmp_dir, p)
                    with open(ofname, 'wb') as of:
                        of.write(inf.read())
                    update_cache(tmp_dir, job, {ofname: ofname})
                    logging.info(f"{p} -> {ofname}")
        #unclaim_job(tmp_dir, job)
    copydirs()
    # Copy spec
    spec = None
    if (args.spec):
        spec = f"{tmp_dir}/in.spec"
        specfile = None
        with open(os.path.join(args.directory, args.spec), 'r') as f:
            specfile = f.read()
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
        outputs = run_basil(tmp_dir, args.args, spec)
    elif args.tool == "boogie":
        outputs = run_boogie(tmp_dir, args.args, spec)
    elif args.tool == "boogie-source":
        outputs = run_boogie_only(tmp_dir, args.args, spec)
    elif args.tool == "boogie-counterexample":
        outputs = pretty_print_counterexample(tmp_dir, args.args, spec)
    else:
        print("Allowed tools: [readelf, bap, basil, boogie, boogie-source, 'boogie-counterexample]")
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
