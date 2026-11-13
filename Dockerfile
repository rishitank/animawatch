# Apify Actor image for AnimaWatch (Standby mode, MCP at /mcp).
# The base image ships Python 3.13 with Playwright 1.65.0 and its browsers.
# Images: https://docs.apify.com/platform/actors/development/base-docker-images
FROM apify/actor-python-playwright:3.13-1.65.0

USER myuser

# Copy only what the package build needs, so source edits do not bust the cache
# of anything but the last layers.
COPY --chown=myuser:myuser pyproject.toml README.md LICENSE ./
COPY --chown=myuser:myuser src ./src

# Keep the Playwright version the image's browsers were installed for: a newer
# Playwright would look for browsers this image does not have.
RUN pip freeze | grep -i '^playwright==' > /tmp/playwright-constraint.txt \
 && echo "Keeping $(cat /tmp/playwright-constraint.txt)" \
 && pip install --no-cache-dir -c /tmp/playwright-constraint.txt . 'apify>=4.0.0,<5' \
 && python -c "import animawatch.actor, animawatch.server" \
 && pip freeze

# Vision stays off unless the user's own key arrives in the Actor input.
ENV VISION_PROVIDER=none

CMD ["animawatch-actor"]
