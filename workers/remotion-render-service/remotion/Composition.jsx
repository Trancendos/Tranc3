const { AbsoluteFill } = require('remotion');
const React = require('react');

/**
 * Minimal title-card composition consumed by the render service.
 * inputProps: { title, description, fps, durationInSeconds }
 */
function TitleCard({ title, description }) {
  return React.createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor: '#1e3a8a',
        color: 'white',
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        fontFamily: 'sans-serif',
      },
    },
    React.createElement('h1', { style: { fontSize: 64 } }, title || ''),
    React.createElement('p', { style: { fontSize: 32 } }, description || ''),
  );
}

module.exports = { TitleCard };
