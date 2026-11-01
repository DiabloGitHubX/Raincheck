
# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "raincheck" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-${var.environment}-vpc"
  }
}


# ---------------------------------------------------------------------------
# Internet Gateway
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "raincheck" {
  vpc_id = aws_vpc.raincheck.id

  tags = {
    Name = "${var.project_name}-${var.environment}-igw"
  }
}


# ---------------------------------------------------------------------------
# Public Subnet
# ---------------------------------------------------------------------------

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.raincheck.id
  availability_zone       = var.availability_zones[0]
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-${var.environment}-public-subnet"
    Type = "public"
  }
}


# ---------------------------------------------------------------------------
# Public Route Table
# ---------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.raincheck.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.raincheck.id
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-public-rt"
  }
}

# ---------------------------------------------------------------------------
# Public Route Table Association
# ---------------------------------------------------------------------------

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
