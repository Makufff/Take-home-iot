// ChirpStack v4 payload codec for the LoRa node (Device profile -> Codec -> JavaScript).
// Uplink: [light_raw_hi, light_raw_lo, light_digital, led]
function decodeUplink(input) {
  var b = input.bytes;
  if (b.length < 4) {
    return { errors: ["expected 4 bytes, got " + b.length] };
  }
  return {
    data: {
      light_raw: (b[0] << 8) | b[1],
      light_digital: b[2],
      led: b[3] === 1
    }
  };
}

// Downlink: { "led": true } -> [0x01]
function encodeDownlink(input) {
  return { bytes: [input.data.led ? 1 : 0] };
}
