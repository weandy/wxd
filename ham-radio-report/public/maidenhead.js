/**
 * Maidenhead Locator System 网格定位转换库
 * 用于保护隐私的位置编码
 */

/**
 * 将经纬度转换为Maidenhead网格定位符（6位精度）
 * @param {number} lat - 纬度 (-90 到 90)
 * @param {number} lon - 经度 (-180 到 180)
 * @returns {string} 6位Maidenhead网格代码，例如: "OM89vc"
 */
function toMaidenhead(lat, lon) {
    // 调整经纬度到正值范围
    let adjustedLon = lon + 180;
    let adjustedLat = lat + 90;

    // Field (第1-2位): 18x18度的大网格
    const fieldLon = String.fromCharCode(65 + Math.floor(adjustedLon / 20));
    const fieldLat = String.fromCharCode(65 + Math.floor(adjustedLat / 10));

    // Square (第3-4位): 2x1度的中网格
    adjustedLon = adjustedLon % 20;
    adjustedLat = adjustedLat % 10;
    const squareLon = Math.floor(adjustedLon / 2);
    const squareLat = Math.floor(adjustedLat / 1);

    // Subsquare (第5-6位): 5x2.5分的小网格
    adjustedLon = (adjustedLon % 2) * 12;
    adjustedLat = (adjustedLat % 1) * 24;
    const subsquareLon = String.fromCharCode(97 + Math.floor(adjustedLon));
    const subsquareLat = String.fromCharCode(97 + Math.floor(adjustedLat));

    return fieldLon + fieldLat + squareLon + squareLat + subsquareLon + subsquareLat;
}

/**
 * 将Maidenhead网格定位符转换为经纬度（网格中心点）
 * @param {string} grid - Maidenhead网格代码，例如: "OM89vc"
 * @returns {object} {lat, lon} 网格中心点的经纬度
 */
function fromMaidenhead(grid) {
    grid = grid.toUpperCase();

    // Field (第1-2位)
    const fieldLon = (grid.charCodeAt(0) - 65) * 20;
    const fieldLat = (grid.charCodeAt(1) - 65) * 10;

    // Square (第3-4位)
    const squareLon = parseInt(grid[2]) * 2;
    const squareLat = parseInt(grid[3]) * 1;

    // Subsquare (第5-6位) - 如果存在
    let subsquareLon = 0;
    let subsquareLat = 0;
    if (grid.length >= 6) {
        subsquareLon = (grid.charCodeAt(4) - 65) / 12;
        subsquareLat = (grid.charCodeAt(5) - 65) / 24;
    }

    // 计算中心点（加上网格大小的一半）
    const lon = fieldLon + squareLon + subsquareLon + (1 / 12) - 180;
    const lat = fieldLat + squareLat + subsquareLat + (1 / 48) - 90;

    return { lat, lon };
}

/**
 * 获取Maidenhead网格的边界框（用于地图显示）
 * @param {string} grid - Maidenhead网格代码
 * @returns {object} {minLat, minLon, maxLat, maxLon}
 */
function getMaidenheadBounds(grid) {
    grid = grid.toUpperCase();

    // Field
    const fieldLon = (grid.charCodeAt(0) - 65) * 20;
    const fieldLat = (grid.charCodeAt(1) - 65) * 10;

    // Square
    const squareLon = parseInt(grid[2]) * 2;
    const squareLat = parseInt(grid[3]) * 1;

    // Subsquare
    let subsquareLon = 0;
    let subsquareLat = 0;
    let lonSize = 2; // 2度
    let latSize = 1; // 1度

    if (grid.length >= 6) {
        subsquareLon = (grid.charCodeAt(4) - 65) / 12;
        subsquareLat = (grid.charCodeAt(5) - 65) / 24;
        lonSize = 1 / 12; // 约5分
        latSize = 1 / 24; // 约2.5分
    } else {
        lonSize = 2;
        latSize = 1;
    }

    const minLon = fieldLon + squareLon + subsquareLon - 180;
    const minLat = fieldLat + squareLat + subsquareLat - 90;
    const maxLon = minLon + lonSize;
    const maxLat = minLat + latSize;

    return {
        minLat,
        minLon,
        maxLat,
        maxLon
    };
}

/**
 * 计算两个Maidenhead网格之间的距离
 * @param {string} grid1 - 第一个网格代码
 * @param {string} grid2 - 第二个网格代码
 * @returns {number} 距离（公里）
 */
function distanceBetweenGrids(grid1, grid2) {
    const coord1 = fromMaidenhead(grid1);
    const coord2 = fromMaidenhead(grid2);

    const R = 6371; // 地球半径 (km)
    const dLat = toRadians(coord2.lat - coord1.lat);
    const dLon = toRadians(coord2.lon - coord1.lon);

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRadians(coord1.lat)) * Math.cos(toRadians(coord2.lat)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function toRadians(degrees) {
    return degrees * (Math.PI / 180);
}

// 导出函数（浏览器环境）
if (typeof window !== 'undefined') {
    window.Maidenhead = {
        toMaidenhead,
        fromMaidenhead,
        getMaidenheadBounds,
        distanceBetweenGrids
    };
}

// 导出函数（Node.js环境）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        toMaidenhead,
        fromMaidenhead,
        getMaidenheadBounds,
        distanceBetweenGrids
    };
}
