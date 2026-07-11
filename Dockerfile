# Aerialist image containing PX4, PX4-Avoidance, ROS, and Gazebo.
# The image is pinned instead of using "latest" for reproducibility.
FROM skhatiri/aerialist:2.0

# Make the Aerialist Python package available inside the container.
RUN pip3 install --no-cache-dir -e /src/aerialist/

# Install the additional dependencies used by TG-MCTS-Elites.
COPY requirements.txt /src/generator/requirements.txt

WORKDIR /src/generator/

RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the generator, case studies, documentation, and scripts.
COPY . /src/generator/

RUN mkdir -p \
    /src/generator/logs \
    /src/generator/results \
    /src/generator/generated_tests

# The generator itself is already inside the Aerialist container in this mode.
ENV AGENT=local

ENV AVOIDANCE_LAUNCH=/src/aerialist/aerialist/resources/simulation/collision_prevention.launch
ENV AVOIDANCE_BOX=/src/aerialist/aerialist/resources/simulation/box.xacro
