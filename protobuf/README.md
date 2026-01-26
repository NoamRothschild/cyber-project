# What is protobuf (and why we need it)

TODO

# Installing protobuff

in order to be able to update the transfer protocol, we would need the protobuf compiler.

### for linux (also for docker):

```bash
sudo apt install protobuf-compiler
```

### for windows:

```bash
winget install protobuf
protoc --version # Ensure compiler version is 3+
```

## Installing the python dependency

in order to be able to use protobuf in python, we would also need its package (same way we install pygame)

```bash
pip install protobuf
```

# Compiling our protobufs

after every change to the protocol, we must recompile it so that python will use the new version.

we do that with this command **(IMPORTANT: run this when the cmd is inside the base game folder)**:

```bash
cd protobuf
protoc --python_out=. --pyi_out=. FILENAME.proto
cd ..
```

where `FILENAME.proto` is the name of the specific protocol

# Using protobuf in python

TODO
