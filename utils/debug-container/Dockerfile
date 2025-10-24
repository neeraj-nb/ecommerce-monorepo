FROM ubuntu:24.04

LABEL maintainer="DevOps Troubleshooter"
LABEL description="Universal DevOps troubleshooting container with networking, infra, and Kubernetes tools"

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=$PATH:/usr/local/bin

# --- Base tools ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git vim nano unzip zip jq \
    iputils-ping dnsutils netcat-traditional telnet tcpdump traceroute nmap iproute2 net-tools lsof socat \
    postgresql-client mysql-client redis-tools \
    python3 python3-pip python3-venv \
    openssh-client ca-certificates gnupg software-properties-common \
 && rm -rf /var/lib/apt/lists/*

# --- Python tools ---
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir \
    httpie \
    requests \
    boto3 \
    psycopg2-binary \
    pymysql \
    redis \
    kubernetes \
    yq \
    ansible

# --- Install kubectl ---
RUN curl -fsSLo /usr/local/bin/kubectl https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl \
 && chmod +x /usr/local/bin/kubectl

# --- Install Helm ---
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# --- Install Terraform ---
RUN curl -fsSL https://releases.hashicorp.com/terraform/$(curl -s https://checkpoint-api.hashicorp.com/v1/check/terraform | jq -r .current_version)/terraform_$(curl -s https://checkpoint-api.hashicorp.com/v1/check/terraform | jq -r .current_version)_linux_amd64.zip -o terraform.zip \
 && unzip terraform.zip -d /usr/local/bin \
 && rm terraform.zip

# --- Install k9s ---
RUN curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz | tar xz -C /usr/local/bin

# --- Install yq & jq (YAML + JSON processing) ---
RUN wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq \
 && chmod +x /usr/local/bin/yq

# --- Convenience scripts ---
RUN echo '#!/bin/bash\nset -e\nhost=$1; port=${2:-80}; until nc -z $host $port; do echo "Waiting for $host:$port..."; sleep 2; done; echo "$host:$port is available."' > /usr/local/bin/wait-for && chmod +x /usr/local/bin/wait-for

WORKDIR /workspace
CMD ["/bin/bash"]
