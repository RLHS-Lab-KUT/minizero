FROM nvidia/cuda:12.8.0-cudnn9-devel-ubuntu22.04
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Taipei

RUN rm /etc/apt/sources.list.d/cuda.list || true && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    vim \
    gdb \
    git \
    less \
    htop \
    wget \
    cmake \
    ffmpeg \
    clang-format \
    python3-pip \
    python3-dev \
    python3-opencv \
    python3-pybind11 \
    libopencv-dev \
    libarchive-tools \
    libboost-all-dev && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    python3 -m pip install -U pip \
    gdown \
    cmake==3.25.2 \
    numpy \
    pandas \
    jupyter \
    matplotlib && \
    python3 -m pip cache purge && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install torch==2.7.0+cu128 \
    --extra-index-url https://download.pytorch.org/whl/cu128 && \
    wget -qO- https://download.pytorch.org/libtorch/cu128/libtorch-cxx11-abi-shared-with-deps-2.7.0%2Bcu128.zip \
    | bsdtar -xvf- -C /usr/local

ENV CMAKE_PREFIX_PATH=/usr/local/libtorch/share/cmake/Torch

RUN mkdir /workspace
WORKDIR /workspace