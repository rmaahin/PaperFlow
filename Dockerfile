FROM nvcr.io/nvidia/pytorch:26.01-py3

WORKDIR /workspace/scientific-paper-pipeline

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1

ENV VIRTUAL_ENV=/opt/env
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    vim \
    tmux \
    htop \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8888 8000 6379

WORKDIR /mnt

CMD ["/bin/bash"]